import json
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Any
import app.config as config

class StorageManager:
    def __init__(self, system_state: config.SystemState):
        self.state_obj = system_state
        self.temperature_history: List[Dict[str, Any]] = []
        self.state_lock = threading.Lock()
        self.history_lock = threading.Lock()

    def normalize_schedule_item(self, job: Dict[str, Any]) -> Dict[str, Any]:
        raw_days = job.get("days", job.get("day", "ALL"))
        candidate_days = [str(d).upper() for d in raw_days] if isinstance(raw_days, (list, tuple, set)) else [str(raw_days).upper()]
        valid_days = [d for d in candidate_days if d in config.DAY_ORDER]
        
        job["days"] = ["ALL"] if not valid_days or "ALL" in valid_days else sorted(list(set(valid_days)), key=lambda d: config.DAY_ORDER[d])
        if "day" in job: 
            del job["day"]

        # Handle modular structural actions safely
        job["action_mode"] = str(job.get("action_mode", job.get("action", "COOL"))).upper()
        if job["action_mode"] not in [m.value for m in config.ACMode]:
            job["action_mode"] = "COOL" if job["action_mode"] == "ON" else "OFF"
            
        job["target_temp"] = float(job.get("target_temp", 24.0))
        job["active"] = bool(job.get("active", True))
        return job

    def parse_days_from_payload(self, data: Dict[str, Any]) -> Any:
        raw_days = data.get("days", data.get("day", "ALL"))
        candidate_days = [str(d).upper() for d in raw_days] if isinstance(raw_days, (list, tuple, set)) else [str(raw_days).upper()]
        valid_days = [d for d in candidate_days if d in config.DAY_ORDER]
        if not valid_days: 
            return None
        return ["ALL"] if "ALL" in valid_days else sorted(list(set(valid_days)), key=lambda d: config.DAY_ORDER[d])

    def save_state(self):
        snapshot = self.state_obj.to_dict()
        # Keep internal volatile details un-persisted
        for volatile_key in ["current_temp", "current_humidity", "ac_power"]:
            if volatile_key in snapshot: 
                del snapshot[volatile_key]
                
        with self.state_lock:
            for path in [config.STATE_FILE, config.STATE_BACKUP_FILE]:
                tmp = path.with_suffix(".tmp")
                with tmp.open("w", encoding="utf-8") as f:
                    json.dump(snapshot, f, indent=2)
                tmp.replace(path)

    def load_state(self):
        chosen_source = config.STATE_FILE if config.STATE_FILE.exists() else (config.STATE_BACKUP_FILE if config.STATE_BACKUP_FILE.exists() else None)
        if not chosen_source: 
            return

        try:
            with chosen_source.open("r", encoding="utf-8") as f:
                data = json.load(f)
                self.state_obj.from_dict(data)
        except Exception as e:
            print(f"Storage Engine Error loading state configurations: {e}")

        if not isinstance(self.state_obj.schedule, list):
            self.state_obj.schedule = config.DEFAULT_STATE["schedule"]
            
        for item in self.state_obj.schedule:
            self.normalize_schedule_item(item)

    def save_history(self):
        with self.history_lock:
            for path in [config.HISTORY_FILE, config.HISTORY_BACKUP_FILE]:
                tmp = path.with_suffix(".tmp")
                with tmp.open("w", encoding="utf-8") as f:
                    json.dump(self.temperature_history, f, indent=2)
                tmp.replace(path)

    def load_history(self) -> List[Dict[str, Any]]:
        chosen_source = config.HISTORY_FILE if config.HISTORY_FILE.exists() else (config.HISTORY_BACKUP_FILE if config.HISTORY_BACKUP_FILE.exists() else None)
        if not chosen_source: 
            return []

        try:
            with chosen_source.open("r", encoding="utf-8") as f:
                data = json.load(f)
                cleaned = []
                for entry in data:
                    if isinstance(entry, dict) and "ts" in entry:
                        cleaned.append({
                            "ts": datetime.fromisoformat(str(entry["ts"])).isoformat(timespec="minutes"),
                            "temp": round(float(entry["temp"]), 2),
                            "humidity": round(float(entry["humidity"]), 2) if entry.get("humidity") is not None else None
                        })
                self.temperature_history = cleaned
                return cleaned
        except Exception:
            return []

    def prune_history(self):
        limit = datetime.now() - timedelta(days=config.HISTORY_RETENTION_DAYS)
        self.temperature_history = [
            row for row in self.temperature_history 
            if datetime.fromisoformat(row["ts"]) >= limit
        ]
        