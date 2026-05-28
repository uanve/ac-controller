from flask import Blueprint, render_template, render_template_string, jsonify, request
from datetime import datetime, timedelta
import app.config as config
from app.storage import StorageManager

api_blueprint = Blueprint('api', __name__)

# References set dynamically during app bootstrapping orchestration
state_ptr: config.SystemState = None
storage_ptr: StorageManager = None

@api_blueprint.route('/apidocs/swagger.json')
def swagger_spec():
    base_url = request.host_url.rstrip('/')
    return jsonify({
        "openapi": "3.0.3",
        "info": {
            "title": "AC Controller API",
            "version": "1.0.0",
            "description": "API for AC control, schedule management, history, and outside sensor ingestion."
        },
        "servers": [{"url": base_url}],
        "paths": {
            "/api/status": {
                "get": {
                    "summary": "Get current AC controller state",
                    "responses": {
                        "200": {"description": "Current state"}
                    }
                }
            },
            "/api/history": {
                "get": {
                    "summary": "Get temperature/humidity history",
                    "parameters": [
                        {
                            "name": "days",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "minimum": 1, "maximum": config.HISTORY_RETENTION_DAYS},
                            "description": "Days of history to return"
                        }
                    ],
                    "responses": {
                        "200": {"description": "History payload"}
                    }
                }
            },
            "/api/outside/report": {
                "post": {
                    "summary": "Ingest outside sensor data (ESP32 push)",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["temperature_C", "humidity_percent", "pressure_hPa"],
                                    "properties": {
                                        "temperature_C": {"type": "number"},
                                        "humidity_percent": {"type": "number"},
                                        "pressure_hPa": {"type": "number"},
                                        "uptime_ms": {"type": "integer"}
                                    }
                                }
                            }
                        }
                    },
                    "parameters": [
                        {
                            "name": "X-Ingest-Token",
                            "in": "header",
                            "required": False,
                            "schema": {"type": "string"},
                            "description": "Required if OUTSIDE_INGEST_TOKEN is configured"
                        }
                    ],
                    "responses": {
                        "200": {"description": "Ingest accepted"},
                        "400": {"description": "Invalid payload"},
                        "401": {"description": "Unauthorized"}
                    }
                }
            },
            "/api/outside/health": {
                "get": {
                    "summary": "Get outside sensor freshness and last values",
                    "responses": {
                        "200": {"description": "Health payload"}
                    }
                }
            },
            "/api/toggle_occupancy": {
                "post": {
                    "summary": "Toggle occupancy mode ON/OFF",
                    "responses": {"200": {"description": "Toggled"}}
                }
            },
            "/api/set_target": {
                "post": {
                    "summary": "Set target temperature",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "target": {"type": "number"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Updated"}}
                }
            },
            "/api/set_target_humidity": {
                "post": {
                    "summary": "Set target humidity",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "target_humidity": {"type": "number"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Updated"}}
                }
            },
            "/api/schedule/master_toggle": {
                "post": {
                    "summary": "Toggle schedule engine",
                    "responses": {"200": {"description": "Toggled"}}
                }
            },
            "/api/schedule/add": {
                "post": {
                    "summary": "Add schedule event",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["time"],
                                    "properties": {
                                        "time": {"type": "string", "example": "08:00"},
                                        "days": {"type": "array", "items": {"type": "string"}},
                                        "action_mode": {"type": "string", "example": "COOL"},
                                        "target_temp": {"type": "number"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {"description": "Added"},
                        "400": {"description": "Validation error"}
                    }
                }
            },
            "/api/schedule/delete": {
                "post": {
                    "summary": "Delete schedule event",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["id"],
                                    "properties": {
                                        "id": {"type": "integer"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Deleted"}}
                }
            }
        }
    })

@api_blueprint.route('/apidocs')
def swagger_ui():
    return render_template_string("""
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>AC Controller API Docs</title>
    <link rel=\"stylesheet\" href=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui.css\" />
    <style>
      html, body { margin: 0; padding: 0; }
      #swagger-ui { max-width: 1200px; margin: 0 auto; }
    </style>
  </head>
  <body>
    <div id=\"swagger-ui\"></div>
    <script src=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js\"></script>
    <script>
      window.ui = SwaggerUIBundle({
        url: '/apidocs/swagger.json',
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [SwaggerUIBundle.presets.apis],
      });
    </script>
  </body>
</html>
    """)

@api_blueprint.route('/')
def index():
    for item in state_ptr.schedule:
        storage_ptr.normalize_schedule_item(item)
    state_ptr.schedule.sort(key=lambda x: (min(config.DAY_ORDER.get(d, 99) for d in x.get("days", ["ALL"])), x["time"]))
    return render_template('index.html', state=state_ptr.to_dict(), week_days=config.WEEK_DAYS)

@api_blueprint.route('/api/status')
def get_status():
    return jsonify(state_ptr.to_dict())

@api_blueprint.route('/api/history')
def get_history():
    try:
        days = int(request.args.get("days", 1))
    except (TypeError, ValueError):
        days = 1
    days = max(1, min(days, config.HISTORY_RETENTION_DAYS))
    cutoff = datetime.now() - timedelta(days=days)
    
    filtered = [
        row for row in storage_ptr.temperature_history
        if datetime.fromisoformat(row["ts"]) >= cutoff
    ]
    return jsonify({"success": True, "days": days, "points": filtered})

@api_blueprint.route('/api/outside/report', methods=['POST'])
def outside_report():
    data = request.get_json(silent=True) or {}

    expected_token = config.OUTSIDE_INGEST_TOKEN.strip()
    if expected_token:
        received_token = request.headers.get("X-Ingest-Token", "")
        if received_token != expected_token:
            return jsonify(success=False, error="unauthorized"), 401

    try:
        state_ptr.outside_temp = round(float(data.get("temperature_C")), 2)
        state_ptr.outside_humidity = round(float(data.get("humidity_percent")), 2)
        state_ptr.outside_pressure = round(float(data.get("pressure_hPa")), 2)
    except (TypeError, ValueError):
        return jsonify(success=False, error="invalid_payload"), 400

    try:
        state_ptr.outside_uptime_ms = int(data.get("uptime_ms", 0))
    except (TypeError, ValueError):
        state_ptr.outside_uptime_ms = 0

    state_ptr.outside_status = "online"
    state_ptr.outside_last_update = datetime.now().isoformat(timespec="seconds")
    return jsonify(success=True)

@api_blueprint.route('/api/outside/health')
def outside_health():
    now_dt = datetime.now()
    last_update = state_ptr.outside_last_update

    age_seconds = None
    if last_update:
        try:
            age_seconds = max(0, int((now_dt - datetime.fromisoformat(last_update)).total_seconds()))
        except ValueError:
            age_seconds = None

    is_fresh = bool(age_seconds is not None and age_seconds <= config.OUTSIDE_SENSOR_STALE_SECONDS)
    computed_status = "online" if is_fresh else "offline"

    return jsonify({
        "success": True,
        "status": computed_status,
        "last_update": last_update,
        "age_seconds": age_seconds,
        "stale_after_seconds": config.OUTSIDE_SENSOR_STALE_SECONDS,
        "outside_temp": state_ptr.outside_temp,
        "outside_humidity": state_ptr.outside_humidity,
        "outside_pressure": state_ptr.outside_pressure,
        "outside_uptime_ms": state_ptr.outside_uptime_ms
    })

@api_blueprint.route('/api/toggle_occupancy', methods=['POST'])
def toggle_occupancy():
    state_ptr.occupancy_mode = "OFF" if state_ptr.occupancy_mode == "ON" else "ON"
    storage_ptr.save_state()
    return jsonify(success=True)

@api_blueprint.route('/api/set_target', methods=['POST'])
def set_target():
    state_ptr.target_temp = float(request.json.get("target", 24))
    state_ptr.temp_override = True
    storage_ptr.save_state()
    return jsonify(success=True)

@api_blueprint.route('/api/set_target_humidity', methods=['POST'])
def set_target_humidity():
    state_ptr.target_humidity = float(request.json.get("target_humidity", 55))
    state_ptr.humidity_override = True
    storage_ptr.save_state()
    return jsonify(success=True)

@api_blueprint.route('/api/schedule/master_toggle', methods=['POST'])
def master_toggle():
    state_ptr.schedule_running = not state_ptr.schedule_running
    storage_ptr.save_state()
    return jsonify(success=True)

@api_blueprint.route('/api/schedule/toggle_active', methods=['POST'])
def toggle_active():
    event_id = int(request.json.get("id"))
    for job in state_ptr.schedule:
        if job["id"] == event_id:
            job["active"] = not job["active"]
            storage_ptr.save_state()
            return jsonify(success=True, new_state=job["active"])
    return jsonify(success=False), 404

@api_blueprint.route('/api/schedule/add', methods=['POST'])
def add_event():
    data = request.json
    days = storage_ptr.parse_days_from_payload(data)
    if not days: 
        return jsonify(success=False, error="Invalid day profile"), 400

    action_mode = str(data.get("action_mode", "COOL")).upper()
    if action_mode not in [m.value for m in config.ACMode]:
        return jsonify(success=False, error="Unsupported AC Mode definition"), 400

    event_time = str(data.get("time", "")).strip()
    if not event_time: 
        return jsonify(success=False, error="Missing timeframe setting"), 400

    new_id = max([item["id"] for item in state_ptr.schedule] + [-1]) + 1
    state_ptr.schedule.append({
        "id": new_id,
        "time": event_time,
        "action_mode": action_mode,
        "target_temp": float(data.get("target_temp", 24.0)),
        "active": True,
        "days": days
    })
    storage_ptr.save_state()
    return jsonify(success=True)

@api_blueprint.route('/api/schedule/delete', methods=['POST'])
def delete_event():
    state_ptr.schedule = [j for j in state_ptr.schedule if j["id"] != request.json.get("id")]
    storage_ptr.save_state()
    return jsonify(success=True)