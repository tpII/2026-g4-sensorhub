# SensorHub - Servidor MCP

Servidor MCP (Model Context Protocol) que expone, como tools invocables por un LLM, la lectura y el comando de los dispositivos de SensorHub. El diseño de qué tool existe, por qué, y de dónde lee cada una está documentado en la wiki, página 06 ([Diseño de Tools MCP por Dispositivo](https://github.com/tpII/2026-g4-sensorhub/wiki/06-Diseno-de-Tools-MCP-por-Dispositivo)) — este README explica cómo levantarlo y probarlo, no el *por qué* de cada decisión.

## Qué hay en esta carpeta

```text
MCP/
├── .env.example           # Plantilla de variables de entorno
├── .env                    # Variables activas (ignorado por Git)
├── devices.csv             # Registro manual de dispositivos (device_type, device_id, nombre amigable)
├── docker-compose.yml      # Levanta el servidor como contenedor en la red del Stack
├── Dockerfile
├── requirements.txt
└── sensorhub_mcp/          # El paquete Python del servidor
    ├── config.py            # Variables de entorno
    ├── mcp_app.py            # Instancia de FastMCP
    ├── mqtt_client.py        # Lectura de mensajes retenidos por MQTT
    ├── influx_client.py      # Consultas Flux a InfluxDB
    ├── devices.py            # Registro y resolución de device_id
    ├── timeutils.py          # Parseo de fechas ISO 8601
    ├── main.py / __main__.py # Punto de entrada
    └── tools/                 # Las tools expuestas al LLM
```

`devices.csv` ya trae los tres dispositivos simulados por defecto:

| device_type | device_id | nombre amigable |
|:---|:---|:---|
| dht | dht_simulado | living |
| pir | pir_simulado | cocina |
| switch | switch_simulado | oficina |

## Prerrequisitos

El servidor MCP no genera datos por sí mismo — lee lo que el Stack y los dispositivos ya publicaron. Antes de probarlo hace falta, en este orden:

1. **El Stack levantado** (EMQX + InfluxDB) — ver [`../Stack/README.md`](../Stack/README.md). Es el que crea la red de Docker (`sensorhub_network`) a la que después se conecta este servidor.
2. **Al menos un simulador publicando** (o, más adelante, el firmware real) — ver [`../Stack/simuladores-mqtt/`](../Stack/simuladores-mqtt/). Sin esto, las tools van a responder correctamente pero sin datos ("no se encontraron lecturas..."), porque no hay nada que leer todavía ni en InfluxDB ni en el tópico MQTT retenido.

```bash
cd ../Stack && docker compose up -d
cd simuladores-mqtt && docker compose up -d simulador-dht simulador-pir simulador-switch
```

## Cómo levantar el servidor MCP

### Opción A — directo con Python (más simple para debuggear)

```bash
cd MCP
cp .env.example .env        # ajustar si hace falta; los defaults ya apuntan a los nombres de contenedor del Stack
pip install -r requirements.txt
python -m sensorhub_mcp
```

Si se corre así (fuera de Docker), hay que pisar `MQTT_BROKER_HOST` e `INFLUXDB_URL` en `.env` para que apunten a `localhost` en vez de a los nombres de contenedor (`sensorhub_emqx` / `sensorhub_influxdb`), ya que esos nombres solo se resuelven dentro de la red de Docker.

### Opción B — como contenedor, dentro de la red del Stack

```bash
cd MCP
docker compose up -d --build
```

Acá no hace falta tocar `.env` — `sensorhub_emqx` y `sensorhub_influxdb` se resuelven solos porque el contenedor se conecta a la misma red (`sensorhub_network`, creada por el Stack).

En ambos casos, el servidor queda escuchando en `http://<MCP_HOST>:<MCP_PORT><MCP_HTTP_PATH>` — por defecto `http://localhost:8000/mcp`.

## Cómo probarlo

### 1. Llamando a las tools directamente en Python (sin protocolo MCP de por medio)

El chequeo más rápido para aislar si el problema es de lógica propia o del protocolo/transporte. Las funciones son Python normal, se pueden importar y llamar sin levantar el servidor:

```bash
cd MCP
python3 -c "
from sensorhub_mcp.tools.device_resolution import resolve_device_id
from sensorhub_mcp.tools.climate import get_current_climate

device_id = resolve_device_id('living')
print(device_id)
print(get_current_climate(device_id))
"
```

### 2. Con el MCP Inspector (recomendado para probar las tools como las vería un LLM, sin necesitar un modelo)

```bash
npx @modelcontextprotocol/inspector
```

Abre una UI local — ahí se configura la conexión como transporte **Streamable HTTP** apuntando a `http://localhost:8000/mcp` (o el host/puerto que corresponda), y desde esa UI se pueden listar e invocar las tools a mano, viendo el JSON de entrada/salida de cada llamada.

### 3. Conectando un cliente real (Claude Desktop, Claude Code, etc.)

Para probar con lenguaje natural de punta a punta, se agrega el servidor como un MCP remoto por URL en la configuración del cliente (`http://localhost:8000/mcp`). Desde ahí, las preguntas al LLM ya pasan por el flujo completo: el modelo elige qué tool llamar, con qué argumentos, y arma la respuesta final a partir de lo que la tool le devuelve.

## Probar desde internet (con modelos públicos o clientes externos)

Como el servidor es HTTP común, alcanza con exponerlo con un túnel — por ejemplo [ngrok](https://ngrok.com/):

```bash
ngrok http 8000
```

Eso da una URL pública (`https://<algo>.ngrok-free.app`). Del lado del cliente externo, se configura el servidor remoto como `https://<algo>.ngrok-free.app/mcp` — tal cual, cambiando solo el host.

**Antes de hacerlo:** las credenciales que usa el servidor (token de InfluxDB, etc.) son las de desarrollo documentadas en [`../Stack/README.md`](../Stack/README.md) — no son secretas, pero tampoco hay que dejar el túnel abierto más tiempo del que dura la prueba, porque cualquiera con la URL puede invocar las tools (incluida `set_switch_state`, el día que exista) mientras el túnel esté activo.
