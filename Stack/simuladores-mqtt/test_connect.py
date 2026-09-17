import sys
import paho.mqtt.client as mqtt

print("Iniciando prueba de conexion TLS hacia mqtt.sensorhub.andy.net.ar:443...")
client = mqtt.Client()
client.tls_set()

def on_connect(c, userdata, flags, rc):
    print(f"[OK] Callback on_connect invocado con codigo: {rc} (0 = exito)")
    c.disconnect()

client.on_connect = on_connect

try:
    client.connect("mqtt.sensorhub.andy.net.ar", 443, 10)
    client.loop_start()
    import time
    time.sleep(3)
    client.loop_stop()
    print("Prueba finalizada.")
except Exception as e:
    print(f"[ERROR] Fallo al conectar: {e}")

