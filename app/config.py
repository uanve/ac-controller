import copy
from pathlib import Path
from enum import Enum
from typing import List, Dict, Any

# --- Modern Modular State Structures ---
class ACMode(str, Enum):
    OFF = "OFF"
    COOL = "COOL"
    DRY = "DRY"   
    HEAT = "HEAT"  

# --- Directory Paths ---
APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
COMMANDS_DIR = PROJECT_ROOT / "commands"

DATA_DIR.mkdir(exist_ok=True)
COMMANDS_DIR.mkdir(exist_ok=True)

# --- Storage Target Files ---
STATE_FILE = DATA_DIR / "state_store.json"
STATE_BACKUP_FILE = DATA_DIR / "state_store.backup.json"
HISTORY_FILE = DATA_DIR / "temperature_history.json"
HISTORY_BACKUP_FILE = DATA_DIR / "temperature_history.backup.json"
OUTSIDE_HISTORY_FILE = DATA_DIR / "outside_temperature_history.json"
OUTSIDE_HISTORY_BACKUP_FILE = DATA_DIR / "outside_temperature_history.backup.json"

# --- Hardware Properties ---
AC_RELAY_PIN = 27 
COOL_COMMAND_FILES = {
    22: COMMANDS_DIR / "cool_22.txt",
    24: COMMANDS_DIR / "cool_24.txt",
    26: COMMANDS_DIR / "cool_26.txt",
}
DRY_COMMAND_FILE = COMMANDS_DIR / "dry.txt"
IR_OFF_FILE = COMMANDS_DIR / "off.txt"
IR_ON_FILE = COOL_COMMAND_FILES[24]
OUTSIDE_SENSOR_URL = "http://192.168.1.160/"
OUTSIDE_SENSOR_TIMEOUT_SECONDS = 1.5
OUTSIDE_SENSOR_POLL_INTERVAL_SECONDS = 30
OUTSIDE_SENSOR_STALE_SECONDS = 1800
OUTSIDE_INGEST_TOKEN = ""


def nearest_cool_command_temp(target_temp: float) -> int:
    target = float(target_temp)
    available = sorted(COOL_COMMAND_FILES.keys())
    return min(available, key=lambda t: abs(t - target))

# --- Constants & Calendars ---
HISTORY_RETENTION_DAYS = 90
WEEK_DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
DAY_ORDER = {"ALL": -1, **{day: idx for idx, day in enumerate(WEEK_DAYS)}}
PERSISTED_KEYS = ["occupancy_mode", "target_temp", "target_humidity", "schedule_running", "schedule"]

class SystemState:
    def __init__(self):
        self.occupancy_mode: str = "OFF"  
        self.ac_power: str = "OFF"         
        self.ac_mode: ACMode = ACMode.COOL 
        
        self.current_temp: float = 0.0
        self.target_temp: float = 24.0
        self.temp_hysteresis: float = 0.5  
        
        self.current_humidity: float = 0.0
        self.target_humidity: float = 55.0
        self.humidity_hysteresis: float = 3.0
        self.temp_override: bool = False
        self.humidity_override: bool = False

        self.outside_status: str = "unknown"
        self.outside_temp: float = 0.0
        self.outside_humidity: float = 0.0
        self.outside_pressure: float = 0.0
        self.outside_uptime_ms: int = 0
        self.outside_last_update: str = ""
        
        self.schedule_running: bool = True
        self.schedule: List[Dict[str, Any]] = [
            {"id": 0, "time": "08:00", "action_mode": "COOL", "target_temp": 23.5, "active": True, "days": ["ALL"]},
            {"id": 1, "time": "18:00", "action_mode": "OFF", "target_temp": 24.0, "active": True, "days": ["ALL"]}
        ]
        self.last_trigger: str = ""
        self.last_ir_command: str = "off"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "occupancy_mode": self.occupancy_mode,
            "ac_power": self.ac_power,
            "ac_mode": self.ac_mode.value,
            "current_temp": self.current_temp,
            "target_temp": self.target_temp,
            "temp_hysteresis": self.temp_hysteresis,
            "current_humidity": self.current_humidity,
            "target_humidity": self.target_humidity,
            "humidity_hysteresis": self.humidity_hysteresis,
            "outside_status": self.outside_status,
            "outside_temp": self.outside_temp,
            "outside_humidity": self.outside_humidity,
            "outside_pressure": self.outside_pressure,
            "outside_uptime_ms": self.outside_uptime_ms,
            "outside_last_update": self.outside_last_update,
            "schedule_running": self.schedule_running,
            "schedule": self.schedule,
            "last_trigger": self.last_trigger,
            "last_ir_command": self.last_ir_command
        }

    def from_dict(self, data: Dict[str, Any]):
        self.occupancy_mode = data.get("occupancy_mode", self.occupancy_mode)
        self.ac_power = data.get("ac_power", self.ac_power)
        
        raw_mode = data.get("ac_mode", "COOL")
        try:
            self.ac_mode = ACMode(raw_mode)
        except ValueError:
            self.ac_mode = ACMode.COOL
            
        self.target_temp = float(data.get("target_temp", self.target_temp))
        self.temp_hysteresis = float(data.get("temp_hysteresis", self.temp_hysteresis))
        self.target_humidity = float(data.get("target_humidity", self.target_humidity))
        self.humidity_hysteresis = float(data.get("humidity_hysteresis", self.humidity_hysteresis))
        self.schedule_running = bool(data.get("schedule_running", self.schedule_running))
        self.schedule = data.get("schedule", self.schedule)
        self.last_trigger = data.get("last_trigger", self.last_trigger)
        self.last_ir_command = str(data.get("last_ir_command", self.last_ir_command))