#!/usr/bin/env python3
import os
import time
import json
import random
import paho.mqtt.client as mqtt


# VARIABLES Y CONFIGURACION

# En Docker se conecta por el nombre del contenedor en la red de docker
BROKER_HOST = os.getenv("BROKER_HOST", "sensorhub_emqx")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
USE_TLS = os.getenv("USE_TLS", "false").lower() in ("true", "1", "yes") or MQTT_PORT in (443, 8883)
TOPICO_TELEMETRIA = os.getenv("TOPICO_TELEMETRIA", "sensorhub/pir/pir_simulado/telemetry")

# Rango aleatorio de espera entre eventos de movimiento
INTERVALO_MIN_SEGUNDOS = int(os.getenv("INTERVALO_MIN_SEGUNDOS", "2"))
INTERVALO_MAX_SEGUNDOS = int(os.getenv("INTERVALO_MAX_SEGUNDOS", "8"))

print(f"Iniciando simulador PIR...")
print(f"Conectando a {BROKER_HOST}:{MQTT_PORT} (TLS: {USE_TLS})...")
print(f"Publicando en topico: {TOPICO_TELEMETRIA}")
print(f"Intervalo aleatorio entre {INTERVALO_MIN_SEGUNDOS}s y {INTERVALO_MAX_SEGUNDOS}s")


# CONEXION MQTT

client = mqtt.Client()
if USE_TLS:
    client.tls_set()

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


# LOOP: Alterna entre movimiento detectado (true) y reposo (false) con intervalo aleatorio

estado_movimiento = False

while True:
    estado_movimiento = not estado_movimiento

    payload = json.dumps({
        "motion": estado_movimiento
    })

    client.publish(TOPICO_TELEMETRIA, payload, qos=1)
    print(f"[{TOPICO_TELEMETRIA}] -> {payload}", flush=True)

    espera = random.randint(INTERVALO_MIN_SEGUNDOS, INTERVALO_MAX_SEGUNDOS)
    time.sleep(espera)
