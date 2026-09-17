#!/usr/bin/env python3
import os
import time
import json
import paho.mqtt.client as mqtt


# VARIABLES Y CONFIGURACION

BROKER_HOST = os.getenv("BROKER_HOST", "sensorhub_emqx")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPICO_COMANDOS = os.getenv("TOPICO_COMANDOS", "sensorhub/switch/switch_simulado/command")
TOPICO_TELEMETRIA = os.getenv("TOPICO_TELEMETRIA", "sensorhub/switch/switch_simulado/telemetry")

print(f"Iniciando simulador de Switch...")
print(f"Conectando a {BROKER_HOST}:{MQTT_PORT}...")
print(f"Topico de comandos  : {TOPICO_COMANDOS}")
print(f"Topico de telemetria: {TOPICO_TELEMETRIA}")


# CALLBACKS MQTT

def on_connect(client, userdata, flags, rc):
    print(f"Conectado exitosamente al broker MQTT!")
    client.subscribe(TOPICO_COMANDOS, qos=1)
    print(f"Suscrito al topico de comandos: {TOPICO_COMANDOS}", flush=True)


def on_message(client, userdata, msg):
    raw_payload = msg.payload.decode("utf-8", errors="ignore")
    try:
        data = json.loads(raw_payload)
        state = data.get("state", "").lower()
    except Exception:
        print(f"[{msg.topic}] -> Payload invalido: {raw_payload}", flush=True)
        return

    if state == "on":
        print(f"[{msg.topic}] -> Recibido 'on'. Prendiendo switch...", flush=True)
    elif state == "off":
        print(f"[{msg.topic}] -> Recibido 'off'. Apagando switch...", flush=True)
    else:
        print(f"[{msg.topic}] -> Comando desconocido: {state}", flush=True)
        return

    # Responder publicando el nuevo estado fisico en el canal de telemetria
    feedback = json.dumps({"state": state})
    client.publish(TOPICO_TELEMETRIA, feedback, qos=1, retain=True)
    print(f"[{TOPICO_TELEMETRIA}] -> {feedback}", flush=True)


# CONEXION MQTT

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

conectado = False
while not conectado:
    try:
        client.connect(BROKER_HOST, MQTT_PORT, 60)
        conectado = True
    except Exception as e:
        print(f"Esperando broker en {BROKER_HOST}:{MQTT_PORT} ({e})... reintentando en 3s")
        time.sleep(3)

print("Esperando comandos... (Presionar Ctrl + C para salir)")
client.loop_forever()

