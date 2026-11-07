#!/usr/bin/env python3
import os
import time
import json
import paho.mqtt.client as mqtt


# VARIABLES Y CONFIGURACION

BROKER_HOST = os.getenv("BROKER_HOST", "sensorhub_emqx")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
# device_id: igual que en el firmware, 12 caracteres hexadecimales en minúsculas (la
# MAC sin separadores). Los simuladores usan un mismo carácter repetido para
# distinguirlos de los dispositivos reales.
DEVICE_ID = os.getenv("DEVICE_ID", "cccccccccccc")
PREFIJO_TOPICOS = "sensorhub"
TOPICO_COMANDOS = f"{PREFIJO_TOPICOS}/switch/{DEVICE_ID}/command"
TOPICO_TELEMETRIA = f"{PREFIJO_TOPICOS}/switch/{DEVICE_ID}/telemetry"
TOPICO_STATUS = f"{PREFIJO_TOPICOS}/switch/{DEVICE_ID}/status"

# Simula un dispositivo sin hora sincronizada (SNTP): igual que el firmware, omite "ts"
# y el broker usa la hora de llegada.
SIN_TS = os.getenv("SIN_TS", "false").lower() in ("true", "1", "yes")


def con_ts(datos):
    if not SIN_TS:
        datos["ts"] = int(time.time() * 1000)
    return datos

print(f"Iniciando simulador de Switch...")
print(f"device_id: {DEVICE_ID}")
print(f"Conectando a {BROKER_HOST}:{MQTT_PORT}...")
print(f"Topico de comandos  : {TOPICO_COMANDOS}")
print(f"Topico de telemetria: {TOPICO_TELEMETRIA}")


# CALLBACKS MQTT

def on_connect(client, userdata, flags, rc):
    print(f"Conectado exitosamente al broker MQTT!")
    client.subscribe(TOPICO_COMANDOS, qos=1)
    print(f"Suscrito al topico de comandos: {TOPICO_COMANDOS}", flush=True)
    client.publish(TOPICO_STATUS, json.dumps(con_ts({"online": True})), qos=1, retain=True)


def on_message(client, userdata, msg):
    # Igual que el firmware: solo atiende su topico de comandos
    if msg.topic != TOPICO_COMANDOS:
        return

    raw_payload = msg.payload.decode("utf-8", errors="ignore")
    try:
        data = json.loads(raw_payload)
    except Exception:
        print(f"[{msg.topic}] -> JSON de comando invalido: {raw_payload}", flush=True)
        return

    # Estandar estricto, igual que el firmware: campo "state" como string, exactamente
    # "on" u "off" en minuscula. Cualquier otra cosa se ignora y no se responde.
    state = data.get("state") if isinstance(data, dict) else None
    if state == "on":
        print(f"[{msg.topic}] -> Recibido 'on'. Prendiendo switch...", flush=True)
    elif state == "off":
        print(f"[{msg.topic}] -> Recibido 'off'. Apagando switch...", flush=True)
    else:
        print(f"[{msg.topic}] -> Payload invalido: se requiere state \"on\" u \"off\" ({raw_payload})", flush=True)
        return

    # Responder publicando el nuevo estado fisico en el canal de telemetria
    feedback = json.dumps(con_ts({"state": state}))
    client.publish(TOPICO_TELEMETRIA, feedback, qos=1, retain=True)
    print(f"[{TOPICO_TELEMETRIA}] -> {feedback}", flush=True)


# CONEXION MQTT

client = mqtt.Client()
if MQTT_USERNAME:
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
client.on_connect = on_connect
client.on_message = on_message
client.will_set(TOPICO_STATUS, json.dumps({"online": False}), qos=1, retain=True)

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

