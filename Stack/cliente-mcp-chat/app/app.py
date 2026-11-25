"""Cliente MCP con chat para SensorHub.

Parte del ejemplo completo de la guía oficial "Build an MCP client" [ https://modelcontextprotocol.io/docs/2026-07-28/develop/build-client#interactive-chat-interface ]
[ https://github.com/modelcontextprotocol/quickstart-resources/tree/main/mcp-client-python ] y solo cambia lo
necesario para: conectarse por red a un servidor MCP remoto con autenticación, usar un modelo
servido por vLLM, mostrarse como página web con el registro (`trace`) de cada mensaje que entra
o sale, y permitir que el servidor le haga preguntas al usuario (elicitation). Sin memoria entre
consultas: cada consulta crea un cliente nuevo."""

import asyncio
import json
import os
from contextlib import AsyncExitStack
from datetime import datetime, timezone

import httpx2
from anthropic import AsyncAnthropic
from fastapi import Body, FastAPI
from fastapi.responses import FileResponse
from mcp import Client, MCPError
from mcp.client import ClientRequestContext
from mcp.client.streamable_http import streamable_http_client
from mcp_types import (
    CallToolResult,
    ElicitRequestParams,
    ElicitResult,
    EmbeddedResource,
    ImageContent,
    Implementation,
    TextContent,
    TextResourceContents,
)

ANTHROPIC_MODEL = os.environ["ANTHROPIC_MODEL"]
# Sonnet 5 thinks adaptively unless told otherwise, and max_tokens caps thinking
# plus the reply, so leave room for both.
MAX_TOKENS = 10000
MAX_TOOL_TURNS = 10
SYSTEM_PROMPT = "Respondé en español, breve y directo. Fecha y hora actual (UTC): {now}."
# Qwen3 "piensa" antes de responder; apagarlo reduce la latencia (extensión de vLLM).
ENABLE_THINKING = os.getenv("ENABLE_THINKING", "false").lower() == "true"
MCP_URL = os.environ["MCP_URL"]
MCP_AUTH_TOKEN = os.environ["MCP_AUTH_TOKEN"]
# Image types the Messages API accepts.
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

app = FastAPI()


def plain(value):
    """Copia de `value` como JSON simple (los bloques del SDK pasan a diccionarios)."""
    return json.loads(json.dumps(value, default=lambda o: o.model_dump(exclude_none=True)))


def tool_result_content(result: CallToolResult) -> list[dict]:
    """Translate an MCP tool result into content for an Anthropic tool_result.

    MCP and Anthropic content blocks differ, so each kind is converted. A kind
    the model cannot take becomes a placeholder rather than vanishing, so the
    model knows something was there.
    """
    content: list[dict] = []
    for block in result.content:
        if isinstance(block, TextContent):
            content.append({"type": "text", "text": block.text})
        elif isinstance(block, ImageContent) and block.mime_type in SUPPORTED_IMAGE_TYPES:
            content.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": block.mime_type, "data": block.data},
                }
            )
        elif isinstance(block, EmbeddedResource) and isinstance(block.resource, TextResourceContents):
            content.append({"type": "text", "text": block.resource.text})
        else:
            content.append({"type": "text", "text": f"[unsupported result type: {block.type}]"})

    content = [block for block in content if block.get("text") != ""]
    has_text = any(isinstance(block, TextContent) and block.text for block in result.content)
    if result.structured_content is not None and not has_text:
        content.append({"type": "text", "text": json.dumps(result.structured_content)})

    return content


# Elicitation: a veces una tool le pide un dato al USUARIO (no al modelo) en medio de la consulta,
# por ejemplo elegir entre dos dispositivos que coinciden con el nombre dado. El cliente deja la
# pregunta acá, la página la muestra (GET /pending/{chat_id}) y la respuesta llega por
# POST /answer/{chat_id}. Hay un casillero por consulta, identificado por el chat_id que genera la
# página, para que dos chats en paralelo no se pisen las preguntas. No se guarda nada después.
PENDING: dict[str, dict] = {}


class MCPClient:
    def __init__(self, trace: list[dict], chat_id: str):
        # Initialize session and client objects
        self.client: Client | None = None
        self.chat_id = chat_id  # casillero de PENDING de esta consulta
        self.exit_stack = AsyncExitStack()
        self._anthropic: AsyncAnthropic | None = None
        self.instructions: str | None = None
        self.tools: list[dict] = []
        self.messages: list[dict] = []
        self.trace = trace  # todo lo que pasa, en orden, para mostrarlo en la página

    @property
    def anthropic(self) -> AsyncAnthropic:
        """Lazy-initialize Anthropic client when needed"""
        if self._anthropic is None:
            # La URL del modelo se toma de ANTHROPIC_BASE_URL (el SDK la lee del entorno).
            self._anthropic = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        return self._anthropic

    async def connect_to_server(self, server_url: str):
        """Connect to an MCP server

        Args:
            server_url: The URL of the server's Streamable HTTP endpoint
        """
        # El encabezado Authorization es la autenticación propia de SensorHub (no es parte de MCP):
        # va en el cliente HTTP que se le entrega al transporte.
        http_client = await self.exit_stack.enter_async_context(
            httpx2.AsyncClient(
                headers={"Authorization": f"Bearer {MCP_AUTH_TOKEN}"},
                timeout=httpx2.Timeout(30.0, read=300.0),
            )
        )
        transport = streamable_http_client(server_url, http_client=http_client)

        # "auto", the SDK's default, probes server/discover, falling back to the
        # 2025-11-25 handshake.
        self.client = await self.exit_stack.enter_async_context(
            Client(
                transport,
                mode="auto",
                client_info=Implementation(name="sensorhub-chat-client", version="1.0.0"),
                elicitation_callback=self.handle_elicitation,
            )
        )
        self.instructions = self.client.instructions

        # The tools are listed once, here; this client doesn't follow later changes.
        response = await self.client.list_tools()
        self.tools = [
            {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}
            for tool in response.tools
        ]
        self.trace.append({"type": "mcp_tools", "instructions": self.instructions, "tools": self.tools})

    async def handle_elicitation(self, context: ClientRequestContext, params: ElicitRequestParams) -> ElicitResult:
        """MCP elicitation: el servidor pregunta, el usuario elige en la página."""
        field, spec = next(iter(params.requested_schema["properties"].items()))
        options = spec["enum"]
        future = asyncio.get_running_loop().create_future()
        PENDING[self.chat_id] = {"message": params.message, "options": options, "future": future}
        try:
            choice = await asyncio.wait_for(future, timeout=300)
        except asyncio.TimeoutError:
            choice = None
        finally:
            PENDING.pop(self.chat_id, None)  # solo se borra el casillero de esta consulta
        self.trace.append({"type": "elicitation", "message": params.message, "options": options, "answer": choice})
        if choice is None:
            return ElicitResult(action="cancel")
        return ElicitResult(action="accept", content={field: choice})

    async def process_query(self, query: str) -> str:
        """Process a query using Claude and available tools"""
        history_length = len(self.messages)
        self.messages.append({"role": "user", "content": query})

        # Instrucciones del servidor MCP + nuestro system prompt mínimo.
        system = SYSTEM_PROMPT.format(now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        if self.instructions:
            system = self.instructions + "\n\n" + system

        final_text = []

        for turn in range(MAX_TOOL_TURNS + 1):
            self.trace.append({"type": "llm_request", "system": system, "messages": plain(self.messages)})
            response = await self.anthropic.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=self.messages,
                tools=self.tools,
                extra_body={"chat_template_kwargs": {"enable_thinking": ENABLE_THINKING}},
            )
            self.trace.append(
                {
                    "type": "llm_response",
                    "message": {"role": "assistant", "content": plain(response.content), "stop_reason": response.stop_reason},
                }
            )

            if response.stop_reason == "refusal":
                # Drop the refused query so a follow-up doesn't send it again.
                del self.messages[history_length:]
                final_text.append("[The model declined to answer; the query is not kept in history]")
                break

            final_text.extend(content.text for content in response.content if content.type == "text")

            if response.stop_reason == "max_tokens":
                final_text.append("[Reply cut off at the max_tokens limit]")
                break
            if response.stop_reason != "tool_use":
                # The API rejects an empty assistant message, so an empty reply isn't kept.
                if response.content:
                    self.messages.append({"role": "assistant", "content": response.content})
                break
            if turn == MAX_TOOL_TURNS:
                final_text.append(f"[Stopped after {MAX_TOOL_TURNS} tool-use turns]")
                break

            tool_results = []
            for tool_use in (content for content in response.content if content.type == "tool_use"):
                try:
                    # call_tool validates the result against the declared schema.
                    result = await self.client.call_tool(tool_use.name, tool_use.input)
                except MCPError as error:
                    # A rejected call is the model's mistake to correct, so it goes
                    # back as a failed tool_result rather than ending the query.
                    # Every tool_use still needs a matching result.
                    self.trace.append(
                        {
                            "type": "tool_call",
                            "name": tool_use.name,
                            "arguments": tool_use.input,
                            "is_error": True,
                            "result": f"Tool call {tool_use.name} failed: {error}",
                        }
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": f"Tool call {tool_use.name} failed: {error}",
                            "is_error": True,
                        }
                    )
                    continue

                content = tool_result_content(result)
                self.trace.append(
                    {
                        "type": "tool_call",
                        "name": tool_use.name,
                        "arguments": tool_use.input,
                        "is_error": bool(result.is_error),
                        "result": "\n".join(block["text"] for block in content if block["type"] == "text"),
                    }
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": content,
                        "is_error": bool(result.is_error),
                    }
                )

            self.messages.append({"role": "assistant", "content": response.content})
            self.messages.append({"role": "user", "content": tool_results})

        return "\n".join(final_text)

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()


# En lugar de chat_loop() y main() de la guía (chat por consola): una página web y sus endpoints.
@app.get("/")
def index():
    return FileResponse("index.html")


@app.get("/pending/{chat_id}")
def pending(chat_id: str):
    return {k: v for k, v in PENDING.get(chat_id, {}).items() if k != "future"}


@app.post("/answer/{chat_id}")
def answer(chat_id: str, body: dict = Body(...)):
    fut = PENDING.get(chat_id, {}).get("future")
    if fut and not fut.done():
        fut.set_result(body.get("choice"))  # None = el usuario canceló
    return {}


@app.post("/chat")
async def chat(body: dict = Body(...)):
    trace: list[dict] = []
    # una conexión y una conversación nuevas por consulta: sin memoria
    client = MCPClient(trace, body["chat_id"])
    try:
        await client.connect_to_server(MCP_URL)
        reply = await client.process_query(body["message"])
        return {"reply": reply, "trace": trace}
    except Exception as e:
        while isinstance(e, BaseExceptionGroup) and e.exceptions:  # TaskGroup oculta la causa real
            e = e.exceptions[0]
        trace.append({"type": "error", "error": str(e)})
        return {"reply": f"Error: {e}", "trace": trace}
    finally:
        await client.cleanup()
