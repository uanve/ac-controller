from flask import Flask, render_template, jsonify, request
import RPi.GPIO as GPIO
import threading
import subprocess
import board
import adafruit_ahtx0
from datetime import datetime
import logging

# --- INITIALIZE FLASK ---
app = Flask(__name__)

# Silence standard request logs
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# --- HARDWARE SETUP ---
AC_RELAY_PIN = 27 
GPIO.setmode(GPIO.BCM)
GPIO.setup(AC_RELAY_PIN, GPIO.OUT, initial=GPIO.LOW)
IR_ON_FILE = "./on_24.txt"
IR_OFF_FILE = "./off.txt"

try:
    i2c = board.I2C()
    sensor = adafruit_ahtx0.AHTx0(i2c)
except Exception as e:
    print(f"Hardware Error: {e}")
    sensor = None

# --- SYSTEM STATE ---
state = {
    "occupancy_mode": "OFF",   
    "ac_power": "OFF",         
    "current_temp": 0.0,
    "target_temp": 24.0,
    "current_humidity": 0.0,   # Tracks actual humidity from sensor
    "target_humidity": 55.0,   # Setpoint target slider
    "schedule_running": True, 
    "schedule": [
        {"id": 0, "time": "08:00", "action": "ON", "active": True},
        {"id": 1, "time": "18:00", "action": "OFF", "active": True}
    ],
    "last_trigger": ""
}

def trigger_ac_hardware(action):
    is_on = (action == "ON")
    filename = IR_ON_FILE if is_on else IR_OFF_FILE
    
    try:
        GPIO.output(AC_RELAY_PIN, GPIO.HIGH if is_on else GPIO.LOW)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG LED -> {'HIGH' if is_on else 'LOW'}")
    except Exception as e:
        print(f"GPIO Debug Error: {e}")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] IR ACTION: Sending {filename}")
    try:
        # subprocess.run(["sudo", "ir-ctl", "-d", "/dev/lirc0", f"--send={filename}"], check=True)
        subprocess.run(["ir-ctl", "-d", "/dev/lirc0", f"--send={filename}"], check=True)
    except Exception as e:
        print(f"IR Blaster Error: {e}")

def update_climate_logic():
    """Calculates if AC should be ON based on Occupancy AND (Temperature OR Humidity)."""
    # Trigger if current temp is past target OR current humidity is past target
    climate_trigger = (state["current_temp"] > state["target_temp"] or 
                       state["current_humidity"] > state["target_humidity"])
    
    should_be_on = (state["occupancy_mode"] == "ON" and climate_trigger)
    new_status = "ON" if should_be_on else "OFF"
    
    if state["ac_power"] != new_status:
        state["ac_power"] = new_status
        trigger_ac_hardware(new_status) 
        print(f"[{datetime.now().strftime('%H:%M:%S')}] SYSTEM STATE UPDATED -> AC UNIT IS {new_status}")

def background_worker():
    """Main loop for sensor reading and automation."""
    ticker = threading.Event()
    while not ticker.wait(2): # Runs every 2 seconds
        # 1. Read Sensor
        if sensor:
            try:
                state["current_temp"] = round(float(sensor.temperature), 1)
                state["current_humidity"] = round(float(sensor.relative_humidity), 1)
            except: 
                pass
        else:
            # Fixed: Explicitly using float decimals for mock data
            state["current_temp"] = 30
            state["current_humidity"] = 100
        
        # 2. Process Schedule
        if state["schedule_running"]:
            now = datetime.now().strftime("%H:%M")
            if state["last_trigger"] != now:
                for job in state["schedule"]:
                    if job["active"] and job["time"] == now:
                        state["occupancy_mode"] = job["action"]
                        state["last_trigger"] = now

        # 3. Apply logic to physical AC
        update_climate_logic()

threading.Thread(target=background_worker, daemon=True).start()

# --- ROUTES ---

@app.route('/')
def index():
    state["schedule"].sort(key=lambda x: x["time"])
    return render_template('index.html', state=state)

@app.route('/api/status')
def get_status():
    return jsonify(state)

@app.route('/api/schedule/toggle_active', methods=['POST'])
def toggle_active():
    data = request.json
    event_id = int(data.get("id"))
    for job in state["schedule"]:
        if job["id"] == event_id:
            job["active"] = not job["active"]
            return jsonify(success=True, new_state=job["active"])
    return jsonify(success=False), 404

@app.route('/api/toggle_occupancy', methods=['POST'])
def toggle_occupancy():
    state["occupancy_mode"] = "OFF" if state["occupancy_mode"] == "ON" else "ON"
    return jsonify(success=True)

@app.route('/api/set_target', methods=['POST'])
def set_target():
    state["target_temp"] = float(request.json.get("target", 24))
    return jsonify(success=True)

@app.route('/api/set_target_humidity', methods=['POST'])
def set_target_humidity():
    state["target_humidity"] = float(request.json.get("target_humidity", 55))
    return jsonify(success=True)

@app.route('/api/schedule/master_toggle', methods=['POST'])
def master_toggle():
    state["schedule_running"] = not state["schedule_running"]
    return jsonify(success=True)

@app.route('/api/schedule/add', methods=['POST'])
def add_event():
    data = request.json
    new_id = max([item["id"] for item in state["schedule"]] + [-1]) + 1
    state["schedule"].append({
        "id": new_id, "time": data["time"], 
        "action": data["action"], "active": True
    })
    return jsonify(success=True)

@app.route('/api/schedule/delete', methods=['POST'])
def delete_event():
    state["schedule"] = [j for j in state["schedule"] if j["id"] != request.json.get("id")]
    return jsonify(success=True)

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000)
    finally:
        GPIO.cleanup()