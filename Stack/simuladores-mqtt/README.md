# Simuladores MQTT

Scripts contenerizados para simular dispositivos IoT (sensores y actuadores) publicando telemetria en EMQX sin requerir hardware fisico real.

---

## Como levantar

Asegurarse de que el stack principal de SensorHub este corriendo (`cd .. && docker compose up -d`). El broker exige usuario y contraseña: copiar `.env.example` a `.env` con las mismas credenciales MQTT de `Stack/.env` (los simuladores de dispositivos usan el usuario de los ESP y el emisor de comandos, el del MCP). Luego:

```bash
# Levantar todos los simuladores (DHT, PIR, Switch y emisor de comandos)
docker compose up --build

# O levantar solo un simulador especifico:
docker compose up --build simulador-dht
docker compose up --build simulador-pir
docker compose up --build simulador-switch
docker compose up --build simulador-switch-commander

# Detener
docker compose down
```

---

## Dispositivos simulados

Cada simulador imita al firmware (ver [`Firmware/sensorHub`](../../Firmware/sensorHub)) y simula **todos los dispositivos de su tipo que figuran en [`MCP/devices.csv`](../../MCP/devices.csv)** (el compose lo monta en `/app/devices.csv`, y se puede cambiar con `DEVICES_CSV`): un cliente MQTT por dispositivo, cada uno con su propio Last Will. Si el archivo no existe, simulan un único dispositivo con `DEVICE_ID`. Con `EXCLUIR_IDS` (ids separados por coma) se omiten dispositivos, por ejemplo los nodos físicos reales, que también figuran en el registro.

| Simulador | `device_id` | Topic de telemetría | `retain` | Qué publica |
|---|---|---|:---:|---|
| `simulador-dht` | todos los `dht` del CSV | `sensorhub/dht/<device_id>/telemetry` | sí | `temperature`, `humidity`, `ts`, cada 10 s (`INTERVALO_SEGUNDOS`). La temperatura sube de 5 en 5 °C de 0 a 50 y la humedad de 6 en 6 puntos de 20 a 80 % (el rango real del DHT11) y vuelve a empezar (cada dispositivo arranca en un punto distinto de la rampa). No se valida el rango: cualquier valor publicado se acepta tal cual |
| `simulador-pir` | todos los `pir` del CSV | `sensorhub/pir/<device_id>/telemetry` | no | `motion`, `ts`: el estado inicial (reposo) al arrancar y después cada cambio, con una espera aleatoria entre 2 y 8 s |
| `simulador-switch` | todos los `switch` del CSV | `sensorhub/switch/<device_id>/telemetry` | sí | Responde a `.../command` con `state`, `ts`. Solo acepta `{"state": "on"}` u `{"state": "off"}` en minúscula; cualquier otra cosa se ignora, igual que el firmware |
| `simulador-switch-commander` | (comanda a todos los `switch` del CSV) | — | no | Manda `on`/`off` alternados cada 4 s a todos |

Todos publican además en `.../status` (QoS 1, `retain`): `{"online": true, "ts": ...}` al conectarse y el Last Will `{"online": false}`. QoS 1 en todo.

**Diferencias con el firmware real**, a tener en cuenta al interpretar los datos:

- El DHT y el PIR generan datos sintéticos (rampa de temperatura, movimiento aleatorio), no lecturas de un sensor.
- El `ts` sale del reloj del contenedor. Con `SIN_TS=true` se omite, como hace el firmware mientras no sincronizó SNTP (el broker usa la hora de llegada).
- Como el firmware, el switch **no publica su estado al arrancar**: hasta recibir el primer comando no hay estado en `telemetry`.
