#!/usr/bin/env python3
import os
import time
import json
import paho.mqtt.client as mqtt


# VARIABLES Y CONFIGURACION

BROKER_HOST = os.getenv("BROKER_HOST", "sensorhub_emqx")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPICO_COMANDOS = os.getenv("TOPICO_COMANDOS", "sensorhub/switch/switch_simulado/command")
INTERVALO_SEGUNDOS = int(os.getenv("INTERVALO_SEGUNDOS", "4"))

print(f"Iniciando emisor de comandos para Switch...")
print(f"Conectando a {BROKER_HOST}:{MQTT_PORT}...")
print(f"Publicando comandos en: {TOPICO_COMANDOS}")
print(f"Intervalo de conmutacion: cada {INTERVALO_SEGUNDOS}s")


# CONEXION MQTT

client = mqtt.Client()

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


# LOOP: Alterna entre comando 'on' y 'off' periodicamente

estado_actual = "off"

while True:
    estado_actual = "on" if estado_actual == "off" else "off"

    payload = json.dumps({
        "state": estado_actual,
        "ts": int(time.time() * 1000)
    })

    client.publish(TOPICO_COMANDOS, payload, qos=1)
    print(f"[{TOPICO_COMANDOS}] -> {payload}", flush=True)

    time.sleep(INTERVALO_SEGUNDOS)

