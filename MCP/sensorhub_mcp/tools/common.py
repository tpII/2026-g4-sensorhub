"""Piezas compartidas por las tools: tipos de parámetros con su descripción y
restricciones (se publican en el JSON Schema de cada tool), anotaciones MCP,
validación de device_id y ejecución de I/O bloqueante fuera del bucle de eventos."""

import functools
from typing import Annotated, Any, Callable, Literal, TypeVar

import anyio
from influxdb_client import InfluxDBClient
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from ..devices import canonical_device_id, find_registered_device, is_safe_device_id
from ..mcp_app import LOG_LEVELS, session_log_level

T = TypeVar("T")

# Tipos de dispositivo del contrato de mensajería (wiki, 03). Como Literal, el
# esquema de la tool los publica como enum y el SDK rechaza cualquier otro valor.
DeviceType = Literal["dht", "pir", "switch"]

# device_id tal como puede escribirlo el usuario: MAC con o sin ':'/'-', en
# cualquier combinación de mayúsculas, o un id simulado (dht_simulado). El
# patrón deja afuera comillas y operadores antes de que el valor llegue al
# código (la validación definitiva se hace sobre la forma canónica).
DeviceIdParam = Annotated[
    str,
    Field(
        description=(
            "device_id del dispositivo: su dirección MAC, 12 caracteres hexadecimales con o sin ':' "
            "(por ejemplo 983dae529858), o un id simulado como dht_simulado. Dado por el usuario o "
            "devuelto por resolve_device_id. No acepta nombres de lugares."
        ),
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_:-]+$",
    ),
]

# Las tools de lectura no modifican nada, devolver lo mismo ante la misma
# entrada es seguro y solo hablan con el broker y la TSDB propios (mundo
# cerrado). Los clientes usan estas pistas, por ejemplo, para no pedir
# confirmación antes de invocarlas.
def read_only(title: str) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


async def run_blocking(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Ejecuta una función bloqueante (MQTT, InfluxDB, lectura del registro) en
    un hilo aparte: si se llamara directo, mientras espera el servidor no
    atendería a ningún otro cliente."""
    return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs))


def influx(ctx: Context) -> InfluxDBClient:
    """Cliente de InfluxDB compartido creado en el lifespan del servidor."""
    return ctx.request_context.lifespan_context.influx


async def validate_device_id(device_id: str, device_type: DeviceType, type_label: str) -> str:
    """Lleva el device_id a su forma canónica, valida su formato y verifica que
    esté registrado con el tipo esperado. Devuelve el id registrado o lanza
    ToolError, que el SDK informa al modelo como resultado con isError=true."""
    canonical = canonical_device_id(device_id)
    if not is_safe_device_id(canonical):
        raise ToolError("El device_id no tiene un formato válido.")
    registered = await run_blocking(find_registered_device, canonical, device_type)
    if registered is None:
        raise ToolError(
            f"'{device_id}' no corresponde a ningún {type_label} registrado. Si el usuario nombró "
            "el dispositivo por un lugar o un apodo, obtener primero el device_id con resolve_device_id."
        )
    return registered


async def log(ctx: Context, level: str, message: str) -> None:
    """Envía un log al cliente por el protocolo MCP si alcanza el nivel que ese
    cliente pidió con logging/setLevel (por defecto, info)."""
    if LOG_LEVELS.index(level) >= LOG_LEVELS.index(session_log_level(ctx.session)):
        await ctx.log(level, message, logger_name="sensorhub")
