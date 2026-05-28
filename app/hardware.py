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

    def send_ir_command(self, power_status: str, mode: config.ACMode):
        """Sends physical commands. Ready for future modular mode expansions."""
        is_on = (power_status == "ON")
        
        try:
            GPIO.output(config.AC_RELAY_PIN, GPIO.HIGH if is_on else GPIO.LOW)
        except Exception as e:
            print(f"GPIO Output Failure: {e}")

        if not is_on:
            file_target = config.IR_OFF_FILE
            print(f"[{datetime.now().strftime('%H:%M:%S')}] IR ACTION -> Sending POWER OFF")
        else:
            if str(mode) == "COOL" or str(mode) == "ACMode.COOL":
                file_target = config.IR_ON_FILE
            elif str(mode) == "DRY" or str(mode) == "ACMode.DRY":
                file_target = config.COMMANDS_DIR / "dry_mode.txt" 
            else:
                file_target = config.IR_ON_FILE
            
            # Extract safe logging name string
            mode_str = mode.value if hasattr(mode, 'value') else str(mode)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] IR ACTION -> Sending POWER ON Mode: {mode_str}")

        try:
            subprocess.run(["ir-ctl", "-d", "/dev/lirc0", f"--send={str(file_target)}"], check=True)
        except Exception as e:
            print(f"IR Transmit execution error: {e}")

    def cleanup(self):
        try:
            GPIO.output(config.AC_RELAY_PIN, GPIO.LOW)
            GPIO.cleanup()
            print("GPIO lines unmounted cleanly.")
        except Exception as e:
            print(f"GPIO Cleanup exception: {e}")