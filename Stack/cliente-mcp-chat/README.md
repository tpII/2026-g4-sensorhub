# Cliente MCP con chat

Compose aparte (no forma parte del Stack base) que levanta un cliente MCP con chat mínimo: una página de chat que conecta con un **modelo remoto que implemente la Messages API de Anthropic** (vLLM la implementa; por ejemplo en otra PC de la tailnet) y le da acceso a las tools del servidor MCP de SensorHub.

El modelo no corre acá: este compose solo levanta el cliente (`app/`). El código sigue la guía oficial [Build an MCP client](https://modelcontextprotocol.io/docs/develop/build-client), y la explicación de cómo se armó está en la wiki, página 08.

## Uso

```bash
# Prerrequisitos: Stack y MCP/ levantados (crean la red sensorhub_network)
cd Stack/cliente-mcp-chat
cp .env.example .env     # completar ANTHROPIC_BASE_URL, ANTHROPIC_MODEL, ANTHROPIC_API_KEY y MCP_AUTH_TOKEN
docker compose up -d --build
```

Abrir <http://localhost:8080> (puerto fijo en el compose). La página muestra el **registro completo** de cada consulta: las tools descubiertas, cada pedido al modelo y su respuesta, cada llamada a una tool con su resultado y, si una tool le hace una pregunta al usuario (*elicitation*, por ejemplo elegir entre dos dispositivos que coinciden con el nombre dado), un botón por opción. El mismo registro viene en el campo `trace` de la respuesta de `POST /chat`.

## Variables (`.env`)

| Variable | Descripción |
|:---|:---|
| `ANTHROPIC_BASE_URL` | Base del endpoint del modelo, **sin** `/v1` (el SDK de Anthropic agrega `/v1/messages`). Usar la IP de Tailscale si el contenedor no resuelve el hostname. |
| `ANTHROPIC_API_KEY` | Token del endpoint, si lo exige. |
| `ANTHROPIC_MODEL` | Id del modelo (`GET <ANTHROPIC_BASE_URL>/v1/models` lo lista). |
| `ENABLE_THINKING` | `true` deja que modelos tipo Qwen3 razonen antes de responder (más lento). Default `false`. |
| `MCP_AUTH_TOKEN` | Mismo valor que en `MCP/.env`. |
| `MCP_URL` | URL del servidor MCP (default `http://sensorhub_mcp:8000/mcp`). |

## Cómo funciona

`app/app.py` expone `GET /` (la página), `POST /chat` (la consulta) y `GET /pending/{chat_id}` + `POST /answer/{chat_id}` (para responder las preguntas de *elicitation*; cada consulta usa su propio `chat_id`, así dos chats en paralelo no se pisan las preguntas). En cada consulta se conecta al servidor MCP, le pasa al modelo la pregunta junto con las tools y las instrucciones del servidor, ejecuta las tools que el modelo pida (hasta 5 vueltas) y devuelve la respuesta final junto con el registro. No guarda nada entre consultas. El system prompt, fijo, incluye la fecha y hora UTC actual para que el modelo pueda convertir "hoy" o "la última hora" a rangos ISO 8601.
