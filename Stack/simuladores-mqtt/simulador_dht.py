#!/usr/bin/env python3
import os
import time
import json
import paho.mqtt.client as mqtt


# VARIABLES Y CONFIGURACIÓN

# En Docker se conecta por el nombre del contenedor en la red de docker
BROKER_HOST = os.getenv("BROKER_HOST", "sensorhub_emqx")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
USE_TLS = os.getenv("USE_TLS", "false").lower() in ("true", "1", "yes") or MQTT_PORT in (443, 8883)
# device_id: igual que en el firmware, 12 caracteres hexadecimales en minúsculas (la
# MAC sin separadores). Los simuladores usan un mismo carácter repetido para
# distinguirlos de los dispositivos reales.
DEVICE_ID = os.getenv("DEVICE_ID", "aaaaaaaaaaaa")
PREFIJO_TOPICOS = "sensorhub"
TOPICO_TELEMETRIA = f"{PREFIJO_TOPICOS}/dht/{DEVICE_ID}/telemetry"
TOPICO_STATUS = f"{PREFIJO_TOPICOS}/dht/{DEVICE_ID}/status"
# El firmware publica cada 10 s (CONFIG_SAMPLE_INTERVAL_MS)
INTERVALO_SEGUNDOS = int(os.getenv("INTERVALO_SEGUNDOS", "10"))

# Simula un dispositivo sin hora sincronizada (SNTP): igual que el firmware, omite "ts"
# y el broker usa la hora de llegada.
SIN_TS = os.getenv("SIN_TS", "false").lower() in ("true", "1", "yes")


def con_ts(datos):
    if not SIN_TS:
        datos["ts"] = int(time.time() * 1000)
    return datos

print(f"Iniciando simulador...")
print(f"Conectando a {BROKER_HOST}:{MQTT_PORT} (TLS: {USE_TLS})...")
print(f"device_id: {DEVICE_ID}")
print(f"Publicando en tópico: {TOPICO_TELEMETRIA}" + (" (sin ts)" if SIN_TS else ""))

# CONEXIÓN MQTT

client = mqtt.Client()
if MQTT_USERNAME:
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
if USE_TLS:
    client.tls_set()

client.will_set(TOPICO_STATUS, json.dumps({"online": False}), qos=1, retain=True)

conectado = False
while not conectado:
    try:
        client.connect(BROKER_HOST, MQTT_PORT, 60)
        conectado = True
        print(f"Conectado exitosamente al broker MQTT!")
    except Exception as e:
        print(f"Esperando broker en {BROKER_HOST}:{MQTT_PORT} ({e})... reintentando en 3s")
        time.sleep(3)

client.loop_start()
client.publish(TOPICO_STATUS, json.dumps(con_ts({"online": True})), qos=1, retain=True)

# LOOP: Incrementa de a 10 grados hasta 90 y vuelve a empezar

while True:
    for i in range(10):
        temperatura = i * 10
        humedad = 50.0

        payload = json.dumps(con_ts({
            "temperature": float(temperatura),
            "humidity": humedad,
        }))

        client.publish(TOPICO_TELEMETRIA, payload, qos=1, retain=True)
        print(f"[{TOPICO_TELEMETRIA}] -> {payload}", flush=True)

        time.sleep(INTERVALO_SEGUNDOS)
