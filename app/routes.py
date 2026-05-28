from flask import Blueprint, render_template, jsonify, request
from datetime import datetime, timedelta
import app.config as config
from app.storage import StorageManager

api_blueprint = Blueprint('api', __name__)

# References set dynamically during app bootstrapping orchestration
state_ptr: config.SystemState = None
storage_ptr: StorageManager = None

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

@api_blueprint.route('/api/toggle_occupancy', methods=['POST'])
def toggle_occupancy():
    state_ptr.occupancy_mode = "OFF" if state_ptr.occupancy_mode == "ON" else "ON"
    storage_ptr.save_state()
    return jsonify(success=True)

@api_blueprint.route('/api/set_target', methods=['POST'])
def set_target():
    state_ptr.target_temp = float(request.json.get("target", 24))
    storage_ptr.save_state()
    return jsonify(success=True)

@api_blueprint.route('/api/set_target_humidity', methods=['POST'])
def set_target_humidity():
    state_ptr.target_humidity = float(request.json.get("target_humidity", 55))
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