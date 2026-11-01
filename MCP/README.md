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
    ├── mcp_app.py            # Instancia de MCPServer: lifespan, instrucciones, opciones de transporte y seguridad HTTP
    ├── resources.py          # Resource sensorhub://device-types
    ├── mqtt_client.py        # Lectura de mensajes retenidos y envío de comandos por MQTT
    ├── influx_client.py      # Consultas Flux a InfluxDB
    ├── devices.py            # Registro y resolución de device_id
    ├── timeutils.py          # Zona horaria y formato de fechas para Flux
    ├── main.py / __main__.py # Punto de entrada
    ├── auth/                  # Autenticación OAuth 2.1 de un solo usuario (ver "Autenticación")
    │   ├── __init__.py         # Validación de la configuración y opciones para MCPServer
    │   ├── provider.py         # Servidor de autorización (interfaz OAuthAuthorizationServerProvider del SDK)
    │   ├── login.py            # Pantalla de login (/oauth/login)
    │   ├── tokens.py           # Access y refresh tokens firmados con HMAC
    │   └── clients.py          # Clientes registrados (DCR) sin estado: el client_id va firmado
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

## Autenticación (OAuth 2.1)

El servidor exige autenticación por defecto (`MCP_AUTH_ENABLED=true`) y no arranca si falta su configuración. Sigue la [especificación de autorización de MCP](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization): el propio servidor hace de servidor de autorización OAuth 2.1 para un único usuario. Los clientes (claude.ai, ChatGPT, Claude Code, MCP Inspector) se registran solos y abren una pantalla de login, donde se ingresa una sola contraseña. Después obtienen tokens con los que llaman a `/mcp`. Informacion completa en la pagina de la wiki, página 05, sección 5 ([Servidor MCP y LLM](https://github.com/tpII/2026-g4-sensorhub/wiki/05-Servidor-MCP-y-LLM)).

### Configuración

En `.env`:

| Variable | Valor |
|:---|:---|
| `MCP_AUTH_ENABLED` | `true` (por defecto). Con `false` el servidor queda abierto: solo para desarrollo local |
| `MCP_PUBLIC_URL` | URL pública del servidor, **sin** path (p. ej. `https://mcp.ejemplo.com`). Es el *issuer* de OAuth; el endpoint protegido es `MCP_PUBLIC_URL` + `MCP_HTTP_PATH` |
| `MCP_AUTH_PASSWORD` | Contraseña de la pantalla de login, de 12 caracteres como mínimo |
| `MCP_AUTH_SECRET` | Clave para firmar tokens y clientes: aleatoria, de 32 caracteres como mínimo y distinta de la contraseña. Se genera con `openssl rand -hex 32` |

Además, el dominio de `MCP_PUBLIC_URL` tiene que estar en `MCP_ALLOWED_HOSTS` (p. ej. `mcp.ejemplo.com`) y en `MCP_ALLOWED_ORIGINS` (`https://mcp.ejemplo.com`).

No hace falta ningún volumen ni base de datos: los tokens y los clientes registrados van firmados, así que un reinicio o un `docker compose up --force-recreate` no desconecta a nadie. Para cambiar las credenciales:

| Qué se cambia | Qué pasa |
|:---|:---|
| `MCP_AUTH_PASSWORD` | Se cierran todas las sesiones. Los conectores siguen configurados con la misma URL y piden login de nuevo |
| `MCP_AUTH_SECRET` | Se invalidan también los clientes registrados: hay que quitar y volver a agregar el conector en cada cliente |

Si el servidor se publica detrás de un proxy, además de `MCP_HTTP_PATH` tiene que dejar pasar las rutas de OAuth: `/.well-known/oauth-*`, `/authorize`, `/token`, `/register` y `/oauth/login`.

### Conectar un cliente

En todos los casos se usa la URL pública completa, `https://<dominio>/mcp`, sin credenciales en la URL:

- **claude.ai** (y Claude Desktop o móvil): *Settings → Connectors → Add custom connector*, con la URL y sin completar Client ID ni Client Secret. Al conectar se abre la pantalla de login de SensorHub. Ver [Add a connector that isn't in the directory](https://claude.com/docs/connectors/custom/remote-mcp).
- **ChatGPT**: se agrega como app o conector con la URL, eligiendo OAuth. ChatGPT se registra por DCR. Ver [Apps SDK — Authentication](https://developers.openai.com/apps-sdk/build/auth).
- **Claude Code**: `claude mcp add --transport http sensorhub https://<dominio>/mcp`, y después `/mcp` para iniciar el login.
- **MCP Inspector**: ver más abajo, en «Cómo probarlo».

La pantalla de login muestra qué cliente pide acceso y a qué sitio va a volver. Si no reconocés el pedido, no ingreses la contraseña. Tras una contraseña incorrecta hay una demora de 1 s, y después de 5 intentos el pedido se descarta y hay que volver a conectar desde el cliente.

### Desarrollo local sin autenticación

Con autenticación activa, todas las URLs del servidor, incluida `http://localhost:8000/mcp`, exigen token, y el login redirige siempre al dominio de `MCP_PUBLIC_URL`. Para probar en local sin dominio, poné `MCP_AUTH_ENABLED=false` en `.env` y recreá el contenedor (`docker compose up -d mcp-server`). Así el servidor queda abierto, como antes de la autenticación; no lo dejes así si es alcanzable desde afuera.

## Cómo probarlo

### 1. Con un cliente MCP mínimo en Python

Las tools son funciones asíncronas que reciben el contexto del servidor (cliente de InfluxDB compartido, sesión del cliente), así que se prueban a través del protocolo, con el cliente oficial del SDK, versión 2 (`pip install "mcp>=2.3,<3"`). Este ejemplo no hace el login OAuth: hay que levantar el servidor con `MCP_AUTH_ENABLED=false` (ver «Desarrollo local sin autenticación»); si no, responde 401. Con el servidor levantado:

```python
import asyncio
import os

from mcp.client.client import Client

# La URL depende de desde dónde corre el cliente (ver la tabla de abajo).
MCP_URL = os.getenv("MCP_URL", "http://localhost:8000/mcp")


async def main():
    async with Client(MCP_URL) as client:
        print([tool.name for tool in (await client.list_tools()).tools])
        result = await client.call_tool("resolve_device_id", {"description": "living"})
        device_id = result.content[0].text
        result = await client.call_tool("get_current_climate", {"device_id": device_id})
        print(result.content[0].text)


asyncio.run(main())
```

La URL del servidor depende de dónde corre. El ejemplo toma el valor de la variable de entorno `MCP_URL` y, si no existe, usa `http://localhost:8000/mcp`:

| Servidor | URL |
|:---|:---|
| Local, en la misma PC donde corre Docker | `http://localhost:8000/mcp` (por defecto) |
| Público, con un dominio | `https://<dominio>/mcp`, por ejemplo `MCP_URL=https://mcp.ejemplo.com/mcp python ejemplo.py`. El dominio hay que agregarlo a `MCP_ALLOWED_HOSTS` y `MCP_ALLOWED_ORIGINS` en `.env`, o el servidor responde 421 o 403 (ver «Probar desde internet») |

Si se cambia `MCP_PORT` en `.env`, el puerto de la URL local tiene que coincidir.

Los errores (dispositivo no registrado, fecha inválida, InfluxDB caído) llegan con `result.is_error == True` (en el protocolo, `isError`). `Client` negocia la revisión más nueva del protocolo (2026-07-28); los clientes de revisiones anteriores también son atendidos.

### 2. Con el MCP Inspector (recomendado para probar las tools como las vería un LLM, sin necesitar un modelo)

**Opción A — ya viene como servicio en `docker-compose.yml`:**

```bash
cd MCP
docker compose up -d mcp-inspector
```

Abri `http://localhost:6274` en el navegador. Como corre en la misma red que `mcp-server`, para conectarlo hay que usar el nombre del contenedor, no `localhost`: **`http://sensorhub_mcp:8000/mcp`** (con `MCP_AUTH_ENABLED=false`).

**Con autenticación activa**, se conecta a la URL pública, igual que un cliente externo:

1. *Transport Type* `Streamable HTTP` y URL `https://<dominio>/mcp`.
2. En *OAuth Settings*, Client ID, Client Secret y Scopes vacíos (si el navegador autocompletó el Client Secret, borrarlo). El Inspector se registra solo.
3. *Connect* abre la pantalla de login de SensorHub; se ingresa `MCP_AUTH_PASSWORD`.

El contenedor del Inspector tiene que poder resolver el dominio. Si el servidor público está en la misma red local y el router no hace NAT *loopback*, el dominio no se alcanza desde adentro con la IP pública. En ese caso, `MCP_PUBLIC_HOST` y `MCP_PUBLIC_HOST_IP` de `.env` lo hacen apuntar a la IP local del servidor dentro del contenedor (`extra_hosts`). El navegador necesita lo mismo en el `/etc/hosts` de la PC, porque la pantalla de login se abre ahí.

> La autenticación de la UI viene deshabilitada (`DANGEROUSLY_OMIT_AUTH`) a propósito, para no tener que copiar un token cada vez en desarrollo local. **No exponer este puerto con ngrok ni publicarlo en otra interfaz** sin volver a habilitar la autenticación — a diferencia del servidor MCP solo, el Inspector es una UI pensada para invocar tools con un click, así que sin token cualquiera que llegue al puerto puede operar los dispositivos.

**Opción B — suelto, sin Docker:**

```bash
npx @modelcontextprotocol/inspector
```

En este caso la URL a conectar es `http://localhost:8000/mcp` (ahí sí vale `localhost`, porque no está corriendo dentro de la red de Docker).

En cualquiera de las dos opciones, una vez conectado se pueden listar e invocar las tools a mano desde la UI, viendo el JSON de entrada/salida de cada llamada.

### 3. Conectando un cliente real (Claude Desktop, Claude Code, etc.)

Para probar con lenguaje natural de punta a punta, se agrega el servidor como un MCP remoto por URL en la configuración del cliente: `http://localhost:8000/mcp` sin autenticación, o la URL pública con autenticación (ver «Conectar un cliente»). Desde ahí, las preguntas al LLM ya pasan por el flujo completo: el modelo elige qué tool llamar, con qué argumentos, y arma la respuesta final a partir de lo que la tool le devuelve.

## Probar desde internet (con modelos públicos o clientes externos)

Como el servidor es HTTP común, alcanza con exponerlo con un túnel — por ejemplo [ngrok](https://ngrok.com/):

```bash
ngrok http 8000
```

Eso da una URL pública (`https://<algo>.ngrok-free.app`). Del lado del cliente externo, se configura el servidor remoto como `https://<algo>.ngrok-free.app/mcp` — tal cual, cambiando solo el host.

El servidor valida los encabezados `Host` y `Origin` (protección contra *DNS rebinding*), así que antes hay que agregar ese dominio en `.env`: `MCP_ALLOWED_HOSTS=...,<algo>.ngrok-free.app` y `MCP_ALLOWED_ORIGINS=...,https://<algo>.ngrok-free.app`. Si no, el servidor responde 421 o 403.

Con autenticación activa, también hay que poner `MCP_PUBLIC_URL=https://<algo>.ngrok-free.app`, porque el login y los metadatos de OAuth se publican con esa URL. Como ngrok cambia el dominio en cada ejecución, los conectores quedan atados a esa URL: al cambiarla hay que volver a agregarlos.

**Antes de hacerlo:** no exponer el servidor con `MCP_AUTH_ENABLED=false`. Sin autenticación, cualquiera con la URL puede invocar las tools (incluida `set_switch_state`) mientras el túnel esté activo.
