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

    def refresh_outside_sensor_status(self, now_dt: datetime):
        if not self.state.outside_last_update:
            self.state.outside_status = "offline"
            return

        try:
            last_dt = datetime.fromisoformat(self.state.outside_last_update)
            age_seconds = (now_dt - last_dt).total_seconds()
            self.state.outside_status = "online" if age_seconds <= config.OUTSIDE_SENSOR_STALE_SECONDS else "offline"
        except Exception:
            self.state.outside_status = "offline"

    def update_climate_logic(self):

        if self.state.occupancy_mode == "OFF":
            if self.state.ac_power != "OFF":
                self.state.ac_power = "OFF"
                self.state.last_ir_command = self.hw.send_ir_command("OFF", self.state.ac_mode, self.state.target_temp)
            return

        current_temp = self.state.current_temp
        target_temp = self.state.target_temp

        current_hum = self.state.current_humidity
        target_hum = self.state.target_humidity

        # Dynamic delta is bypassed right after user target adjustments.
        effective_temp_delta = 0 if self.state.temp_override else self.state.temp_hysteresis
        effective_hum_delta = 0 if self.state.humidity_override else self.state.humidity_hysteresis

        is_cooling = (self.state.ac_power == "ON" and self.state.ac_mode == config.ACMode.COOL)
        is_drying = (self.state.ac_power == "ON" and self.state.ac_mode == config.ACMode.DRY)

        if is_cooling:
            needs_cooling = current_temp > target_temp
        else:
            needs_cooling = current_temp > (target_temp + effective_temp_delta)

        if is_drying:
            needs_drying = current_hum > target_hum
        else:
            needs_drying = current_hum > (target_hum + effective_hum_delta)

        if current_temp <= target_temp:
            self.state.temp_override = False
        if current_hum <= target_hum:
            self.state.humidity_override = False

        desired_power = "OFF"
        desired_mode = self.state.ac_mode

        if needs_cooling:
            desired_power = "ON"
            desired_mode = config.ACMode.COOL

        elif needs_drying:
            desired_power = "ON"
            desired_mode = config.ACMode.DRY

        mode_changed = desired_mode != self.state.ac_mode
        power_changed = desired_power != self.state.ac_power
        _, desired_command_name = self.hw.resolve_ir_target(desired_power, desired_mode, target_temp)
        command_changed = desired_command_name != str(self.state.last_ir_command)

        if power_changed or mode_changed or command_changed:
            self.state.ac_power = desired_power
            self.state.ac_mode = desired_mode
            self.state.last_ir_command = self.hw.send_ir_command(desired_power, desired_mode, target_temp)

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
            loop_sleep = max(1.0, float(getattr(config, "ENGINE_LOOP_INTERVAL_SECONDS", 5.0)))
            while True:
                self.state.current_temp, self.state.current_humidity = self.hw.read_sensors()
                now = datetime.now()
                self.refresh_outside_sensor_status(now)
                
                self.append_history_sample(now)
                self.process_schedule(now)
                self.update_climate_logic()
                
                time.sleep(loop_sleep)

        t = threading.Thread(target=run, daemon=True)
        t.start()