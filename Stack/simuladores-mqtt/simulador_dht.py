#!/usr/bin/env python3
import json
import os
import threading
import time

from comun import (BROKER_HOST, MQTT_PORT, USE_TLS, PREFIJO_TOPICOS, SIN_TS,
                   con_ts, conectar, crear_cliente, dispositivos)

# Un hilo y un cliente MQTT por cada DHT de devices.csv. El firmware publica cada 10 s.
INTERVALO_SEGUNDOS = int(os.getenv("INTERVALO_SEGUNDOS", "10"))


def simular(device_id, desfase):
    topico = f"{PREFIJO_TOPICOS}/dht/{device_id}/telemetry"
    status = f"{PREFIJO_TOPICOS}/dht/{device_id}/status"
    client = crear_cliente(status)
    conectar(client)
    client.loop_start()
    client.publish(status, json.dumps(con_ts({"online": True})), qos=1, retain=True)
    # Recorre temperatura de 0 a 50 °C y humedad de 20 a 80 % en 11 pasos y vuelve a empezar;
    # el desfase evita que todos los sensores publiquen el mismo valor.
    i = desfase
    while True:
        payload = json.dumps(con_ts({"temperature": float((i % 11) * 5), "humidity": 20.0 + (i % 11) * 6.0}))
        client.publish(topico, payload, qos=1, retain=True)
        print(f"[{topico}] -> {payload}", flush=True)
        i += 1
        time.sleep(INTERVALO_SEGUNDOS)


ids = dispositivos("dht", "aaaaaaaaaaaa")
print(f"Iniciando simulador DHT: {len(ids)} dispositivos -> {BROKER_HOST}:{MQTT_PORT} (TLS: {USE_TLS})"
      + (" (sin ts)" if SIN_TS else ""), flush=True)
for n, did in enumerate(ids):
    print(f"  device_id: {did}", flush=True)
    threading.Thread(target=simular, args=(did, n * 3), daemon=True).start()
while True:
    time.sleep(3600)
