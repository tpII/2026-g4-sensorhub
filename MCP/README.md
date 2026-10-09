# SensorHub - Servidor MCP

Servidor MCP (Model Context Protocol) que expone, como tools invocables por un LLM, la lectura y el comando de los dispositivos de SensorHub. El diseño de qué tool existe, por qué, y de dónde lee cada una está documentado en la wiki, página 06 ([Diseño de Tools MCP por Dispositivo](https://github.com/tpII/2026-g4-sensorhub/wiki/06-Diseno-de-Tools-MCP-por-Dispositivo)) — este README explica cómo levantarlo y probarlo, no el *por qué* de cada decisión.

## Qué hay en esta carpeta

```text
MCP/
├── .env.example           # Plantilla de variables de entorno
├── .env                    # Variables activas (ignorado por Git)
├── devices.csv             # Registro manual de dispositivos (device_type, device_id, nombre amigable)
├── docker-compose.yml      # Levanta el servidor y, opcionalmente, el MCP Inspector
├── Dockerfile
├── requirements.txt
└── sensorhub_mcp/          # El paquete Python del servidor
    ├── config.py            # Variables de entorno
    ├── mcp_app.py            # Instancia de FastMCP: lifespan, seguridad HTTP, instrucciones, logging
    ├── resources.py          # Resource sensorhub://device-types
    ├── mqtt_client.py        # Lectura de mensajes retenidos por MQTT
    ├── influx_client.py      # Consultas Flux a InfluxDB
    ├── devices.py            # Registro y resolución de device_id
    ├── timeutils.py          # Zona horaria y formato de fechas para Flux
    ├── main.py / __main__.py # Punto de entrada
    └── tools/                 # Las tools expuestas al LLM (common.py: tipos y helpers compartidos)
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

### 1. Con un cliente MCP mínimo en Python

Las tools son funciones asíncronas que reciben el contexto del servidor (cliente de InfluxDB compartido, sesión del cliente), así que se prueban a través del protocolo, con el cliente oficial del SDK (`pip install mcp`). Con el servidor levantado:

```python
import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print([tool.name for tool in (await session.list_tools()).tools])
            result = await session.call_tool("resolve_device_id", {"description": "living"})
            device_id = result.content[0].text
            result = await session.call_tool("get_current_climate", {"device_id": device_id})
            print(result.content[0].text)


asyncio.run(main())
```

Los errores (dispositivo no registrado, fecha inválida, InfluxDB caído) llegan con `result.isError == True`.

### 2. Con el MCP Inspector (recomendado para probar las tools como las vería un LLM, sin necesitar un modelo)

**Opción A — ya viene como servicio en `docker-compose.yml`:**

```bash
cd MCP
docker compose up -d mcp-inspector
```

Abri `http://localhost:6274` en el navegador. Como corre en la misma red que `mcp-server`, para conectarlo hay que usar el nombre del contenedor, no `localhost`: **`http://sensorhub_mcp:8000/mcp`**.

> La autenticación de la UI viene deshabilitada (`DANGEROUSLY_OMIT_AUTH`) a propósito, para no tener que copiar un token cada vez en desarrollo local. **No exponer este puerto con ngrok ni publicarlo en otra interfaz** sin volver a habilitar la autenticación — a diferencia del servidor MCP solo, el Inspector es una UI pensada para invocar tools con un click, así que sin token cualquiera que llegue al puerto puede operar los dispositivos.

**Opción B — suelto, sin Docker:**

```bash
npx @modelcontextprotocol/inspector
```

En este caso la URL a conectar es `http://localhost:8000/mcp` (ahí sí vale `localhost`, porque no está corriendo dentro de la red de Docker).

En cualquiera de las dos opciones, una vez conectado se pueden listar e invocar las tools a mano desde la UI, viendo el JSON de entrada/salida de cada llamada.

### 3. Conectando un cliente real (Claude Desktop, Claude Code, etc.)

Para probar con lenguaje natural de punta a punta, se agrega el servidor como un MCP remoto por URL en la configuración del cliente (`http://localhost:8000/mcp`). Desde ahí, las preguntas al LLM ya pasan por el flujo completo: el modelo elige qué tool llamar, con qué argumentos, y arma la respuesta final a partir de lo que la tool le devuelve.

## Probar desde internet (con modelos públicos o clientes externos)

Como el servidor es HTTP común, alcanza con exponerlo con un túnel — por ejemplo [ngrok](https://ngrok.com/):

```bash
ngrok http 8000
```

Eso da una URL pública (`https://<algo>.ngrok-free.app`). Del lado del cliente externo, se configura el servidor remoto como `https://<algo>.ngrok-free.app/mcp` — tal cual, cambiando solo el host.

El servidor valida los encabezados `Host` y `Origin` (protección contra *DNS rebinding*), así que antes hay que agregar ese dominio en `.env`: `MCP_ALLOWED_HOSTS=...,<algo>.ngrok-free.app` y `MCP_ALLOWED_ORIGINS=...,https://<algo>.ngrok-free.app`. Si no, el servidor responde 421 o 403.

**Antes de hacerlo:** las credenciales que usa el servidor (token de InfluxDB, etc.) son las de desarrollo documentadas en [`../Stack/README.md`](../Stack/README.md) — no son secretas, pero tampoco hay que dejar el túnel abierto más tiempo del que dura la prueba, porque cualquiera con la URL puede invocar las tools (incluida `set_switch_state`, el día que exista) mientras el túnel esté activo.
