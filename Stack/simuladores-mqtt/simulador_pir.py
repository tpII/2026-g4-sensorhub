#!/usr/bin/env python3
import json
import os
import random
import threading
import time

from comun import (BROKER_HOST, MQTT_PORT, USE_TLS, PREFIJO_TOPICOS, SIN_TS,
                   con_ts, conectar, crear_cliente, dispositivos)

# Rango aleatorio de espera entre eventos de movimiento
INTERVALO_MIN_SEGUNDOS = int(os.getenv("INTERVALO_MIN_SEGUNDOS", "2"))
INTERVALO_MAX_SEGUNDOS = int(os.getenv("INTERVALO_MAX_SEGUNDOS", "8"))


def simular(device_id):
    topico = f"{PREFIJO_TOPICOS}/pir/{device_id}/telemetry"
    status = f"{PREFIJO_TOPICOS}/pir/{device_id}/status"
    client = crear_cliente(status)
    conectar(client)
    client.loop_start()
    client.publish(status, json.dumps(con_ts({"online": True})), qos=1, retain=True)
    # Como el firmware: estado inicial (reposo) al arrancar y después solo los cambios,
    # con espera aleatoria entre ellos. Telemetría sin retain.
    movimiento = False
    while True:
        payload = json.dumps(con_ts({"motion": movimiento}))
        client.publish(topico, payload, qos=1)
        print(f"[{topico}] -> {payload}", flush=True)
        time.sleep(random.randint(INTERVALO_MIN_SEGUNDOS, INTERVALO_MAX_SEGUNDOS))
        movimiento = not movimiento


ids = dispositivos("pir", "bbbbbbbbbbbb")
print(f"Iniciando simulador PIR: {len(ids)} dispositivos -> {BROKER_HOST}:{MQTT_PORT} (TLS: {USE_TLS})"
      + (" (sin ts)" if SIN_TS else ""), flush=True)
print(f"Intervalo aleatorio entre {INTERVALO_MIN_SEGUNDOS}s y {INTERVALO_MAX_SEGUNDOS}s", flush=True)
for did in ids:
    print(f"  device_id: {did}", flush=True)
    threading.Thread(target=simular, args=(did,), daemon=True).start()
while True:
    time.sleep(3600)
