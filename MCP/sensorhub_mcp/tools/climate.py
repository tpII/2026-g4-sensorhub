"""Tools de clima (DHT: temperatura y humedad) — ver wiki, 06, sección 3.1."""

import time
from datetime import datetime, timedelta, timezone
from typing import Annotated

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

from ..influx_client import query_field_aggregate, query_latest_climate
from ..mcp_app import mcp
from ..mqtt_client import fetch_mqtt_retained
from ..timeutils import as_utc, to_flux_time
from .common import DeviceIdParam, influx, log, read_only, run_blocking, validate_device_id

# Cuán viejo puede ser el `ts` de un mensaje retenido por MQTT antes de
# avisar explícitamente que puede no reflejar el estado actual del
# dispositivo (no es un TTL de caché — retain nunca expira solo, así que
# esto es lo único que distingue "el dispositivo recién publicó esto" de
# "esto es lo último que se supo de él, puede estar desconectado hace
# rato" — ver la discusión sobre el DHT apagado hace horas, wiki 03 sección 6).
MQTT_STALE_AFTER_SECONDS = 30

# Ventana hacia atrás para buscar la lectura vigente en un timestamp pedido
# (get_climate_at) — mismo criterio y mismo valor que MQTT_STALE_AFTER_SECONDS,
# porque es la misma pregunta de fondo ("¿hace cuánto no publica el DHT?"),
# solo que referida a un instante del pasado en vez de a ahora. Si no hay
# nada en ese rango, se informa en vez de devolver un dato de hace
# demasiado tiempo.
CLIMATE_AT_WINDOW_SECONDS = 60

INFLUX_UNAVAILABLE = "No se pudo consultar InfluxDB en este momento; reintentar en unos segundos."

# Fechas: el tipo datetime publica el formato date-time (ISO 8601) en el
# esquema y el SDK rechaza valores que no lo cumplan antes de llamar a la tool.
Timestamp = Annotated[
    datetime,
    Field(
        description=(
            "Instante en formato ISO 8601 (por ejemplo 2026-10-02T15:00:00Z); sin zona horaria se "
            "interpreta como UTC. Convertir a este formato las horas que el usuario exprese en "
            "lenguaje natural."
        )
    ),
]


async def _dht(device_id: str) -> str:
    return await validate_device_id(device_id, "dht", "sensor DHT")


@mcp.tool(annotations=read_only("Clima actual de un sensor"))
async def get_current_climate(device_id: DeviceIdParam, ctx: Context) -> str:
    """
    Obtiene la temperatura y la humedad actuales de un sensor DHT, con la
    hora de la lectura. Si el usuario dio el device_id del sensor, usarlo
    directamente; si nombró el sensor por un lugar o un apodo ("el living"),
    llamar primero a resolve_device_id.
    """
    device_id = await _dht(device_id)

    retained = await run_blocking(fetch_mqtt_retained, f"sensorhub/dht/{device_id}/telemetry")
    if retained is not None and "temperature" in retained and "humidity" in retained and "ts" in retained:
        ts = retained["ts"]
        age_seconds = time.time() - (ts / 1000)
        time_str = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        base = (
            f"La temperatura del sensor '{device_id}' es {float(retained['temperature']):.1f}°C "
            f"y la humedad es {float(retained['humidity']):.1f}% (registradas a las {time_str})."
        )
        if age_seconds > MQTT_STALE_AFTER_SECONDS:
            base += " Es el último dato reportado; el sensor podría estar desconectado desde entonces."
        return base

    await log(ctx, "debug", f"Sin mensaje retenido para '{device_id}'; se consulta InfluxDB")
    try:
        temp_val, hum_val, time_str = await run_blocking(query_latest_climate, influx(ctx), device_id)
    except Exception as e:
        await log(ctx, "error", f"Error consultando InfluxDB: {e}")
        raise ToolError(INFLUX_UNAVAILABLE) from e

    if temp_val is None and hum_val is None:
        return f"No se encontraron lecturas de clima en las últimas 24h para el sensor '{device_id}'."

    partes = []
    if temp_val is not None:
        partes.append(f"la temperatura es {float(temp_val):.1f}°C")
    if hum_val is not None:
        partes.append(f"la humedad es {float(hum_val):.1f}%")
    return f"Para el sensor '{device_id}', " + " y ".join(partes) + f" (registradas a las {time_str})."


@mcp.tool(annotations=read_only("Clima en un instante"))
async def get_climate_at(device_id: DeviceIdParam, timestamp: Timestamp, ctx: Context) -> str:
    """
    Obtiene la temperatura y humedad que estaban vigentes en un momento
    puntual del pasado, buscando la última lectura registrada hasta ese
    instante. Si el usuario nombró el sensor por un lugar o un apodo, llamar
    primero a resolve_device_id; si dio su device_id, usarlo directamente.
    """
    device_id = await _dht(device_id)
    moment = as_utc(timestamp)
    start_rfc3339 = to_flux_time(moment - timedelta(seconds=CLIMATE_AT_WINDOW_SECONDS))
    stop_rfc3339 = to_flux_time(moment + timedelta(seconds=1))

    try:
        client = influx(ctx)
        temp_val, temp_time = await run_blocking(
            query_field_aggregate, client, "dht_telemetry", "temperature", device_id, "last", start_rfc3339, stop_rfc3339
        )
        hum_val, hum_time = await run_blocking(
            query_field_aggregate, client, "dht_telemetry", "humidity", device_id, "last", start_rfc3339, stop_rfc3339
        )
    except Exception as e:
        await log(ctx, "error", f"Error consultando InfluxDB: {e}")
        raise ToolError(INFLUX_UNAVAILABLE) from e

    moment_str = moment.strftime("%Y-%m-%d %H:%M:%S UTC")
    if temp_val is None and hum_val is None:
        return (
            f"No hay lecturas del sensor '{device_id}' en los {CLIMATE_AT_WINDOW_SECONDS}s "
            f"previos a {moment_str}."
        )

    partes = []
    if temp_val is not None:
        partes.append(f"la temperatura era {float(temp_val):.1f}°C (registrada a las {temp_time})")
    if hum_val is not None:
        partes.append(f"la humedad era {float(hum_val):.1f}% (registrada a las {hum_time})")
    return f"Para el sensor '{device_id}', " + " y ".join(partes) + "."


@mcp.tool(annotations=read_only("Tendencia del clima en un rango"))
async def get_climate_trend(
    device_id: DeviceIdParam,
    start: Annotated[datetime, Field(description="Inicio del rango, en formato ISO 8601 (por ejemplo 2026-10-02T10:00:00Z).")],
    end: Annotated[datetime, Field(description="Fin del rango, en formato ISO 8601; debe ser posterior al inicio.")],
    ctx: Context,
) -> str:
    """
    Resume cómo varió la temperatura y la humedad de un sensor DHT entre dos
    instantes (mínimo, máximo y promedio) — no devuelve la serie completa,
    sino un resumen en lenguaje natural de la tendencia. Si el usuario nombró
    el sensor por un lugar o un apodo, llamar primero a resolve_device_id; si
    dio su device_id, usarlo directamente.
    """
    device_id = await _dht(device_id)
    start_dt, end_dt = as_utc(start), as_utc(end)
    if start_dt >= end_dt:
        raise ToolError("El inicio del rango tiene que ser anterior al fin.")

    start_rfc3339, stop_rfc3339 = to_flux_time(start_dt), to_flux_time(end_dt)
    client = influx(ctx)

    def aggregate(field: str, agg: str):
        return query_field_aggregate(client, "dht_telemetry", field, device_id, agg, start_rfc3339, stop_rfc3339)[0]

    try:
        temp_min, temp_max, temp_mean, hum_min, hum_max, hum_mean = [
            await run_blocking(aggregate, field, agg)
            for field in ("temperature", "humidity")
            for agg in ("min", "max", "mean")
        ]
    except Exception as e:
        await log(ctx, "error", f"Error consultando InfluxDB: {e}")
        raise ToolError(INFLUX_UNAVAILABLE) from e

    rango = f"{start_dt.strftime('%Y-%m-%d %H:%M')} y {end_dt.strftime('%Y-%m-%d %H:%M')} UTC"
    if temp_mean is None and hum_mean is None:
        return f"No hay lecturas del sensor '{device_id}' entre {rango}."

    partes = []
    if temp_mean is not None:
        partes.append(
            f"la temperatura varió entre {float(temp_min):.1f}°C y {float(temp_max):.1f}°C "
            f"(promedio {float(temp_mean):.1f}°C)"
        )
    if hum_mean is not None:
        partes.append(
            f"la humedad varió entre {float(hum_min):.1f}% y {float(hum_max):.1f}% "
            f"(promedio {float(hum_mean):.1f}%)"
        )
    return f"Entre {rango}, para el sensor '{device_id}', " + "; y ".join(partes) + "."
