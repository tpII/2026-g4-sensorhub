"""Utilidades compartidas por los simuladores: configuración, registro de dispositivos
y conexión MQTT."""
import csv
import json
import os
import time
import paho.mqtt.client as mqtt

BROKER_HOST = os.getenv("BROKER_HOST", "sensorhub_emqx")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
USE_TLS = os.getenv("USE_TLS", "false").lower() in ("true", "1", "yes") or MQTT_PORT in (443, 8883)
PREFIJO_TOPICOS = "sensorhub"
# Registro de dispositivos (el mismo MCP/devices.csv que usa el servidor MCP).
DEVICES_CSV = os.getenv("DEVICES_CSV", "/app/devices.csv")
# ids que no se simulan (por ejemplo, nodos físicos reales), separados por coma.
EXCLUIR_IDS = {i.strip().lower() for i in os.getenv("EXCLUIR_IDS", "").split(",") if i.strip()}
# Simula un dispositivo sin hora sincronizada (SNTP): igual que el firmware, omite "ts"
# y el broker usa la hora de llegada.
SIN_TS = os.getenv("SIN_TS", "false").lower() in ("true", "1", "yes")


def con_ts(datos):
    if not SIN_TS:
        datos["ts"] = int(time.time() * 1000)
    return datos


def dispositivos(tipo, defecto):
    """device_id de todos los dispositivos del tipo indicado que figuran en devices.csv.
    Si el archivo no existe, usa la variable DEVICE_ID (o `defecto`)."""
    ids = []
    if os.path.exists(DEVICES_CSV):
        with open(DEVICES_CSV, newline="", encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                did = fila["device_id"].strip().lower()
                if fila["device_type"].strip().lower() == tipo and did and did not in ids:
                    ids.append(did)
    else:
        ids = [os.getenv("DEVICE_ID", defecto)]
    return [i for i in ids if i not in EXCLUIR_IDS]


def crear_cliente(will_topic=None, **kw):
    client = mqtt.Client(**kw)
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    if USE_TLS:
        client.tls_set()
    if will_topic:
        client.will_set(will_topic, json.dumps({"online": False}), qos=1, retain=True)
    return client


def conectar(client):
    while True:
        try:
            client.connect(BROKER_HOST, MQTT_PORT, 60)
            return
        except Exception as e:
            print(f"Esperando broker en {BROKER_HOST}:{MQTT_PORT} ({e})... reintentando en 3s", flush=True)
            time.sleep(3)
