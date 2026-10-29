"""Piezas compartidas por las tools: tipos de parámetros con su descripción y
restricciones (se publican en el JSON Schema de cada tool), anotaciones MCP,
validación de device_id y ejecución de I/O bloqueante fuera del bucle de eventos."""

import functools
from datetime import datetime, timezone
from typing import Annotated, Any, Callable, Literal, TypeVar

import anyio
from influxdb_client import InfluxDBClient
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from ..devices import canonical_device_id, find_registered_device, is_safe_device_id
from ..timeutils import as_utc

T = TypeVar("T")

INFLUX_UNAVAILABLE = "No se pudo consultar InfluxDB en este momento; reintentar en unos segundos."

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

RangeStartParam = Annotated[
    datetime,
    Field(
        description=(
            "Inicio del rango en formato ISO 8601 (por ejemplo 2026-10-29T10:00:00Z); sin zona "
            "horaria se interpreta como UTC. Convertir a este formato las expresiones relativas del "
            "usuario ('hoy', 'en la última hora')."
        )
    ),
]

RangeEndParam = Annotated[
    datetime,
    Field(
        description=(
            "Fin del rango en formato ISO 8601; debe ser posterior al inicio. Si supera la hora "
            "actual (por ejemplo al consultar 'hoy'), se recorta automáticamente al instante actual."
        )
    ),
]


def normalize_past_range(start: datetime, end: datetime) -> tuple[datetime, datetime, bool]:
    """Valida un rango temporal histórico `[start, end]` llevándolo a UTC y
    recortando `end` al instante actual si cae en el futuro."""
    start_dt, end_dt = as_utc(start), as_utc(end)
    if start_dt >= end_dt:
        raise ToolError("El inicio del rango tiene que ser anterior al fin.")

    now_dt = datetime.now(timezone.utc)
    if start_dt >= now_dt:
        raise ToolError("El inicio del rango está en el futuro; indicar un período ya transcurrido.")

    clamped = end_dt > now_dt
    effective_end = now_dt if clamped else end_dt
    return start_dt, effective_end, clamped

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


# Las tools de comando sobre actuadores modifican el mundo físico (no son de
# solo lectura y se marcan destructivas para que el cliente pueda pedir
# confirmación, ver wiki 05 sección 3.2), pero fijar un estado explícito
# ("on"/"off") es idempotente (wiki 03 sección 6) y opera en mundo cerrado.
def actuator_command(title: str) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        readOnlyHint=False,
        destructiveHint=True,
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
