import time
import threading
from datetime import datetime
import app.config as config
from app.storage import StorageManager
from app.hardware import HardwareManager

class ClimateLogicEngine:
    def __init__(self, state_instance: config.SystemState, storage_mgr: StorageManager, hw_mgr: HardwareManager):
        self.state = state_instance
        self.storage = storage_mgr
        self.hw = hw_mgr
        self.last_history_slot = None

    def update_climate_logic(self):
        """
        Executes an advanced Hysteresis curve calculation context.
        Prevents rapid physical cycling of hardware relays.
        """
        # If occupancy logic dictates shutdown, switch off immediately
        if self.state.occupancy_mode == "OFF":
            if self.state.ac_power != "OFF":
                self.state.ac_power = "OFF"
                self.hw.send_ir_command("OFF", self.state.ac_mode)
            return

        current_temp = self.state.current_temp
        target_temp = self.state.target_temp
        temp_delta = self.state.temp_hysteresis

        current_hum = self.state.current_humidity
        target_hum = self.state.target_humidity
        hum_delta = self.state.humidity_hysteresis

        # Core evaluation matrices with explicit logic guards
        should_activate = (current_temp > (target_temp + temp_delta)) or (current_hum > (target_hum + hum_delta))
        should_deactivate = (current_temp < (target_temp - temp_delta)) and (current_hum < (target_hum - hum_delta))

        new_status = self.state.ac_power # Default to maintaining current state

        if self.state.ac_power == "OFF" and should_activate:
            new_status = "ON"
        elif self.state.ac_power == "ON" and should_deactivate:
            new_status = "OFF"

        if self.state.ac_power != new_status:
            self.state.ac_power = new_status
            self.hw.send_ir_command(new_status, self.state.ac_mode)

    def process_schedule(self, now_dt: datetime):
        if not self.state.schedule_running:
            return

        now_str = now_dt.strftime("%H:%M")
        today_str = config.WEEK_DAYS[now_dt.weekday()]

        if self.state.last_trigger != now_str:
            for event in self.state.schedule:
                selected_days = event.get("days", ["ALL"])
                is_applicable = ("ALL" in selected_days or today_str in selected_days)
                
                if event["active"] and is_applicable and event["time"] == now_str:
                    action_mode = event["action_mode"]
                    
                    if action_mode == "OFF":
                        self.state.occupancy_mode = "OFF"
                    else:
                        self.state.occupancy_mode = "ON"
                        try:
                            self.state.ac_mode = config.ACMode(action_mode)
                        except ValueError:
                            self.state.ac_mode = config.ACMode.COOL
                        
                        # Dynamically apply the schedule's requested target temperature
                        self.state.target_temp = float(event.get("target_temp", 24.0))

                    self.state.last_trigger = now_str
                    self.storage.save_state()

    def append_history_sample(self, now_dt: datetime):
        if now_dt.minute % 5 != 0: 
            return
        slot = now_dt.strftime("%Y-%m-%dT%H:%M")
        if self.last_history_slot == slot: 
            return

        self.storage.temperature_history.append({
            "ts": slot,
            "temp": round(self.state.current_temp, 2),
            "humidity": round(self.state.current_humidity, 2)
        })
        self.last_history_slot = slot
        self.storage.prune_history()
        self.storage.save_history()

    def start_engine_loop(self):
        """Spawns the background telemetry worker thread context."""
        def run():
            while True:
                self.state.current_temp, self.state.current_humidity = self.hw.read_sensors()
                now = datetime.now()
                
                self.append_history_sample(now)
                self.process_schedule(now)
                self.update_climate_logic()
                
                time.sleep(2)

        t = threading.Thread(target=run, daemon=True)
        t.start()