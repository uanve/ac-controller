from __future__ import annotations
import subprocess
from datetime import datetime
import RPi.GPIO as GPIO
import board
import adafruit_ahtx0
import app.config as config

class HardwareManager:
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(config.AC_RELAY_PIN, GPIO.OUT, initial=GPIO.LOW)
        
        try:
            self.i2c = board.I2C()
            self.sensor = adafruit_ahtx0.AHTx0(self.i2c)
            print("Hardware Manager: AHTx0 environmental sensor online.")
        except Exception as e:
            print(f"Hardware Manager: Physical Sensor not found ({e}). Using mock fallback mode.")
            self.sensor = None

    def read_sensors(self) -> tuple:
        if self.sensor:
            try:
                return (round(float(self.sensor.temperature), 1), 
                        round(float(self.sensor.relative_humidity), 1))
            except Exception:
                pass
        return (28.5, 62.0)  

    def resolve_ir_target(self, power_status: str, mode: config.ACMode, target_temp: float = 24.0):
        is_on = (str(power_status).upper() == "ON")
        mode_str = mode.value if hasattr(mode, 'value') else str(mode)
        normalized_mode = str(mode_str).upper().replace("ACMODE.", "")

        if not is_on or normalized_mode == "OFF":
            return (config.IR_OFF_FILE, "off")

        if normalized_mode == "DRY":
            return (config.DRY_COMMAND_FILE, "dry")

        cool_temp = config.nearest_cool_command_temp(target_temp)
        return (config.COOL_COMMAND_FILES[cool_temp], f"cool_{cool_temp}")

    def send_ir_command(self, power_status: str, mode: config.ACMode, target_temp: float = 24.0) -> str:
        """Send IR command and return the normalized command name (e.g. cool_24, dry, off)."""
        is_on = (power_status == "ON")
        file_target, command_name = self.resolve_ir_target(power_status, mode, target_temp)
        
        try:
            GPIO.output(config.AC_RELAY_PIN, GPIO.HIGH if is_on else GPIO.LOW)
        except Exception as e:
            print(f"GPIO Output Failure: {e}")

        if not is_on:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] IR ACTION -> Sending POWER OFF")
        else:
            mode_str = mode.value if hasattr(mode, 'value') else str(mode)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] IR ACTION -> Sending POWER ON Mode: {mode_str} Command: {command_name}")

        try:
            subprocess.run(["ir-ctl", "-d", "/dev/lirc0", f"--send={str(file_target)}"], check=True)
        except Exception as e:
            print(f"IR Transmit execution error: {e}")

        return command_name

    def cleanup(self):
        try:
            GPIO.output(config.AC_RELAY_PIN, GPIO.LOW)
            GPIO.cleanup()
            print("GPIO lines unmounted cleanly.")
        except Exception as e:
            print(f"GPIO Cleanup exception: {e}")