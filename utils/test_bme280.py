import time
import board
import busio
from adafruit_bme280 import advanced as adafruit_bme280

# Inicializar I2C y sensor BME280
i2c = busio.I2C(board.SCL, board.SDA)
bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)

# Opcional: Calibración de presión
bme280.sea_level_pressure = 1013.25

while True:
    temp = bme280.temperature
    hum = bme280.humidity
    pres = bme280.pressure
    
    print(f"Temp: {temp:.1f}°C | Hum: {hum:.1f}% | Pres: {pres:.1f}hPa")
    time.sleep(5)