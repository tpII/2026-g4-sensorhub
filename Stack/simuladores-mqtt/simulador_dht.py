#!/usr/bin/env python3
import os
import time
import json
import paho.mqtt.client as mqtt


# VARIABLES Y CONFIGURACIÓN

# En Docker se conecta por el nombre del contenedor en la red de docker
BROKER_HOST = os.getenv("BROKER_HOST", "sensorhub_emqx")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
USE_TLS = os.getenv("USE_TLS", "false").lower() in ("true", "1", "yes") or MQTT_PORT in (443, 8883)
TOPICO_TELEMETRIA = os.getenv("TOPICO_TELEMETRIA", "sensorhub/dht/dht_simulado/telemetry")
TOPICO_STATUS = os.getenv("TOPICO_STATUS", "sensorhub/dht/dht_simulado/status")
INTERVALO_SEGUNDOS = int(os.getenv("INTERVALO_SEGUNDOS", "2"))

print(f"Iniciando simulador...")
print(f"Conectando a {BROKER_HOST}:{MQTT_PORT} (TLS: {USE_TLS})...")
print(f"Publicando en tópico: {TOPICO_TELEMETRIA}")

# CONEXIÓN MQTT

client = mqtt.Client()
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
client.publish(TOPICO_STATUS, json.dumps({"online": True}), qos=1, retain=True)

# LOOP: Incrementa de a 10 grados hasta 90 y vuelve a empezar

while True:
    for i in range(10):
        temperatura = i * 10
        humedad = 50.0

        payload = json.dumps({
            "temperature": float(temperatura),
            "humidity": humedad
        })

        client.publish(TOPICO_TELEMETRIA, payload, qos=1, retain=True)
        print(f"[{TOPICO_TELEMETRIA}] -> {payload}", flush=True)

        time.sleep(INTERVALO_SEGUNDOS)
