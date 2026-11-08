#!/usr/bin/env python3
import json
import time

from comun import (BROKER_HOST, MQTT_PORT, PREFIJO_TOPICOS,
                   con_ts, conectar, crear_cliente, dispositivos)

# Un cliente MQTT por cada switch de devices.csv; todos usan los mismos callbacks y
# se distinguen por el device_id guardado en userdata.


def on_connect(client, device_id, flags, rc):
    comandos = f"{PREFIJO_TOPICOS}/switch/{device_id}/command"
    client.subscribe(comandos, qos=1)
    print(f"[{device_id}] conectado; suscrito a {comandos}", flush=True)
    client.publish(f"{PREFIJO_TOPICOS}/switch/{device_id}/status", json.dumps(con_ts({"online": True})), qos=1, retain=True)


def on_message(client, device_id, msg):
    # Igual que el firmware: solo atiende su tópico de comandos
    if msg.topic != f"{PREFIJO_TOPICOS}/switch/{device_id}/command":
        return
    raw = msg.payload.decode("utf-8", errors="ignore")
    try:
        data = json.loads(raw)
    except Exception:
        print(f"[{msg.topic}] -> JSON de comando invalido: {raw}", flush=True)
        return
    # Estándar estricto, igual que el firmware: "state" exactamente "on" u "off" en
    # minúscula. Cualquier otra cosa se ignora y no se responde.
    state = data.get("state") if isinstance(data, dict) else None
    if state not in ("on", "off"):
        print(f"[{msg.topic}] -> Payload invalido: se requiere state \"on\" u \"off\" ({raw})", flush=True)
        return
    print(f"[{msg.topic}] -> Recibido '{state}'", flush=True)
    topico = f"{PREFIJO_TOPICOS}/switch/{device_id}/telemetry"
    feedback = json.dumps(con_ts({"state": state}))
    client.publish(topico, feedback, qos=1, retain=True)
    print(f"[{topico}] -> {feedback}", flush=True)


ids = dispositivos("switch", "cccccccccccc")
print(f"Iniciando simulador de Switch: {len(ids)} dispositivos -> {BROKER_HOST}:{MQTT_PORT}", flush=True)
clientes = []
for did in ids:
    c = crear_cliente(f"{PREFIJO_TOPICOS}/switch/{did}/status", userdata=did)
    c.on_connect = on_connect
    c.on_message = on_message
    conectar(c)
    c.loop_start()
    clientes.append(c)
print("Esperando comandos... (Ctrl + C para salir)", flush=True)
while True:
    time.sleep(3600)
