#!/usr/bin/env python3
import json
import os
import time

from comun import BROKER_HOST, MQTT_PORT, PREFIJO_TOPICOS, conectar, crear_cliente, dispositivos

INTERVALO_SEGUNDOS = int(os.getenv("INTERVALO_SEGUNDOS", "4"))

ids = dispositivos("switch", "cccccccccccc")
print(f"Emisor de comandos para {len(ids)} switches -> {BROKER_HOST}:{MQTT_PORT}; cada {INTERVALO_SEGUNDOS}s", flush=True)
client = crear_cliente()
conectar(client)
client.loop_start()

# Alterna 'on' y 'off' en todos los switches.
estado = "off"
while True:
    estado = "on" if estado == "off" else "off"
    for did in ids:
        topico = f"{PREFIJO_TOPICOS}/switch/{did}/command"
        payload = json.dumps({"state": estado, "ts": int(time.time() * 1000)})
        client.publish(topico, payload, qos=1)
        print(f"[{topico}] -> {payload}", flush=True)
    time.sleep(INTERVALO_SEGUNDOS)
