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

Cada simulador imita al firmware (ver [`Firmware/sensorHub`](../../Firmware/sensorHub)) y usa un `device_id` con el mismo formato que los reales: 12 caracteres hexadecimales en minúsculas (la MAC sin separadores), con un mismo carácter repetido para distinguirlos. Se cambia con la variable `DEVICE_ID`. Los mismos ids están registrados en [`MCP/devices.csv`](../../MCP/devices.csv).

| Simulador | `device_id` | Topic de telemetría | `retain` | Qué publica |
|---|---|---|:---:|---|
| `simulador-dht` | `aaaaaaaaaaaa` | `sensorhub/dht/aaaaaaaaaaaa/telemetry` | sí | `temperature`, `humidity`, `ts`, cada 10 s (`INTERVALO_SEGUNDOS`). La temperatura sube de 10 en 10 °C de 0 a 90 y vuelve a empezar; la humedad es fija en 50 % |
| `simulador-pir` | `bbbbbbbbbbbb` | `sensorhub/pir/bbbbbbbbbbbb/telemetry` | no | `motion`, `ts`: el estado inicial (reposo) al arrancar y después cada cambio, con una espera aleatoria entre 2 y 8 s |
| `simulador-switch` | `cccccccccccc` | `sensorhub/switch/cccccccccccc/telemetry` | sí | Responde a `.../command` con `state`, `ts`. Solo acepta `{"state": "on"}` u `{"state": "off"}` en minúscula; cualquier otra cosa se ignora, igual que el firmware |
| `simulador-switch-commander` | (comanda a `cccccccccccc`) | — | no | Manda `on`/`off` alternados cada 4 s |

Todos publican además en `.../status` (QoS 1, `retain`): `{"online": true, "ts": ...}` al conectarse y el Last Will `{"online": false}`. QoS 1 en todo.

**Diferencias con el firmware real**, a tener en cuenta al interpretar los datos:

- El DHT y el PIR generan datos sintéticos (rampa de temperatura, movimiento aleatorio), no lecturas de un sensor.
- El `ts` sale del reloj del contenedor. Con `SIN_TS=true` se omite, como hace el firmware mientras no sincronizó SNTP (el broker usa la hora de llegada).
- Como el firmware, el switch **no publica su estado al arrancar**: hasta recibir el primer comando no hay estado en `telemetry`.
