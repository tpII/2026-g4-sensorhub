"""Tools de actuador Switch (relé / iluminación: comando y consultas de estado)
— ver wiki, 06, sección 3.3."""

import logging
import time
from datetime import datetime, timezone
from typing import Annotated, Literal

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from ..influx_client import (
    StateRangeSummary,
    query_latest_telemetry,
    query_state_series,
    summarize_binary_state_range,
)
from ..mcp_app import mcp
from ..mqtt_client import (
    MQTT_COMMAND_TIMEOUT_SECONDS,
    MqttBrokerError,
    fetch_mqtt_retained,
    publish_command_and_wait_feedback,
)
from .common import (
    INFLUX_UNAVAILABLE,
    DeviceIdParam,
    RangeEndParam,
    RangeStartParam,
    actuator_command,
    influx,
    normalize_past_range,
    read_only,
    run_blocking,
    validate_device_id,
)

logger = logging.getLogger(__name__)

MQTT_UNAVAILABLE = "No se pudo comunicar con el broker MQTT en este momento; reintentar en unos segundos."

SwitchStateParam = Annotated[
    Literal["on", "off"],
    Field(
        description=(
            "Estado deseado para el actuador, en minúsculas: 'on' para encender o 'off' para apagar."
        )
    ),
]


async def _switch(device_id: str) -> str:
    return await validate_device_id(device_id, "switch", "actuador switch")


def _state_label(state: str) -> str:
    return "encendido" if state == "on" else "apagado"


def _format_duration(total_seconds: float) -> str:
    secs = int(round(total_seconds))
    if secs <= 0:
        return "0 s"
    hours, rem = divmod(secs, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours} h")
    if minutes:
        parts.append(f"{minutes} min")
    if seconds or not parts:
        parts.append(f"{seconds} s")
    return " ".join(parts)


async def _query_switch_summary(
    ctx: Context, device_id: str, start_dt: datetime, end_dt: datetime
) -> StateRangeSummary:
    try:
        prior_val, raw_points = await run_blocking(
            query_state_series,
            influx(ctx),
            "switch_telemetry",
            "state",
            device_id,
            start_dt,
            end_dt,
        )
    except Exception as e:
        logger.error("Error consultando InfluxDB para switch '%s': %s", device_id, e)
        raise ToolError(INFLUX_UNAVAILABLE) from e

    prior_active = True if prior_val == "on" else (False if prior_val == "off" else None)
    bool_points = [(ts, val == "on") for ts, val in raw_points if val in ("on", "off")]
    return summarize_binary_state_range(prior_active, bool_points, start_dt, end_dt)


@mcp.tool(annotations=actuator_command("Cambiar estado de un switch"))
async def set_switch_state(device_id: DeviceIdParam, state: SwitchStateParam) -> str:
    """
    Enciende ('on') o apaga ('off') un actuador switch (por ejemplo una luz o
    un relé) enviando el comando por MQTT y esperando la confirmación física del
    dispositivo en telemetría antes de responder. Si el usuario nombró el
    actuador por un lugar o un apodo ("la luz de la oficina"), llamar primero a
    resolve_device_id con device_type='switch'; si dio su device_id, usarlo
    directamente.
    """
    device_id = await _switch(device_id)
    cmd_topic = f"sensorhub/switch/{device_id}/command"
    tel_topic = f"sensorhub/switch/{device_id}/telemetry"
    cmd_payload = {"state": state, "ts": int(time.time() * 1000)}

    try:
        feedback = await run_blocking(
            publish_command_and_wait_feedback,
            cmd_topic,
            tel_topic,
            cmd_payload,
            "state",
            state,
            MQTT_COMMAND_TIMEOUT_SECONDS,
        )
    except MqttBrokerError as e:
        raise ToolError(MQTT_UNAVAILABLE) from e

    if feedback is None:
        raise ToolError(
            f"Se envió la orden '{state}' al switch '{device_id}', pero no se recibió confirmación "
            f"física en {MQTT_COMMAND_TIMEOUT_SECONDS:.0f}s. El dispositivo podría estar apagado o "
            "sin conexión."
        )

    fb_ts = feedback.get("ts")
    if isinstance(fb_ts, (int, float)) and fb_ts > 0:
        time_str = datetime.fromtimestamp(fb_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    return f"El switch '{device_id}' quedó {_state_label(state)} ('{state}', confirmado a las {time_str})."


@mcp.tool(annotations=read_only("Estado actual de un switch"))
async def get_switch_state(device_id: DeviceIdParam, ctx: Context) -> str:
    """
    Consulta si un actuador switch está actualmente encendido ('on') o apagado
    ('off'), sin modificar su estado, junto con la hora del último cambio
    confirmado. Si el usuario nombró el actuador por un lugar o un apodo ("la
    oficina"), llamar primero a resolve_device_id con device_type='switch'; si
    dio su device_id, usarlo directamente.
    """
    device_id = await _switch(device_id)

    retained = await run_blocking(fetch_mqtt_retained, f"sensorhub/switch/{device_id}/telemetry")
    if retained is not None and retained.get("state") in ("on", "off"):
        state = retained["state"]
        ts = retained.get("ts")
        if isinstance(ts, (int, float)) and ts > 0:
            time_str = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            return (
                f"El switch '{device_id}' está {_state_label(state)} "
                f"('{state}', confirmado a las {time_str})."
            )
        return f"El switch '{device_id}' está {_state_label(state)} ('{state}')."

    logger.debug("Sin mensaje retenido para switch '%s'; se consulta InfluxDB", device_id)
    try:
        state_val, time_str = await run_blocking(
            query_latest_telemetry, influx(ctx), "switch_telemetry", "state", device_id
        )
    except Exception as e:
        logger.error("Error consultando InfluxDB para switch '%s': %s", device_id, e)
        raise ToolError(INFLUX_UNAVAILABLE) from e

    if state_val not in ("on", "off"):
        return f"No se encontraron registros de estado en las últimas 24h para el switch '{device_id}'."

    return (
        f"El switch '{device_id}' está {_state_label(state_val)} "
        f"('{state_val}', último registro a las {time_str})."
    )


@mcp.tool(annotations=read_only("Tiempo encendido de un switch en un rango"))
async def get_switch_on_duration(
    device_id: DeviceIdParam,
    start: RangeStartParam,
    end: RangeEndParam,
    ctx: Context,
) -> str:
    """
    Calcula cuánto tiempo acumulado estuvo encendido ('on') un actuador switch
    entre dos instantes, recorriendo sus transiciones de estado en InfluxDB. Si
    el usuario nombró el actuador por un lugar o un apodo, llamar primero a
    resolve_device_id con device_type='switch'; si dio su device_id, usarlo
    directamente.
    """
    device_id = await _switch(device_id)
    start_dt, effective_end, _ = normalize_past_range(start, end)
    summary = await _query_switch_summary(ctx, device_id, start_dt, effective_end)

    rango = (
        f"{start_dt.strftime('%Y-%m-%d %H:%M:%S')} y "
        f"{effective_end.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    if not summary.had_data:
        return f"No hay registros del switch '{device_id}' entre {rango}."

    dur_str = _format_duration(summary.active_seconds)
    extra = " (continúa encendido al cierre del período)" if summary.currently_active else ""
    return f"Entre {rango}, el switch '{device_id}' estuvo encendido durante {dur_str}{extra}."


@mcp.tool(annotations=read_only("Cantidad de encendidos de un switch en un rango"))
async def count_switch_toggles(
    device_id: DeviceIdParam,
    start: RangeStartParam,
    end: RangeEndParam,
    ctx: Context,
) -> str:
    """
    Cuenta cuántas veces se encendió (transiciones a 'on') y se apagó
    (transiciones a 'off') un actuador switch dentro de un rango de tiempo. Si
    el usuario nombró el actuador por un lugar o un apodo, llamar primero a
    resolve_device_id con device_type='switch'; si dio su device_id, usarlo
    directamente.
    """
    device_id = await _switch(device_id)
    start_dt, effective_end, _ = normalize_past_range(start, end)
    summary = await _query_switch_summary(ctx, device_id, start_dt, effective_end)

    rango = (
        f"{start_dt.strftime('%Y-%m-%d %H:%M:%S')} y "
        f"{effective_end.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    if not summary.had_data:
        return f"No hay registros de actividad del switch '{device_id}' entre {rango}."

    if summary.activations == 0 and summary.deactivations == 0:
        estado_fijo = "encendido" if summary.prior_active else "apagado"
        return (
            f"Entre {rango}, el switch '{device_id}' no cambió de estado "
            f"(0 encendidos y 0 apagados; permaneció {estado_fijo})."
        )

    enc_str = "1 vez" if summary.activations == 1 else f"{summary.activations} veces"
    apag_str = "1 vez" if summary.deactivations == 1 else f"{summary.deactivations} veces"
    return f"Entre {rango}, el switch '{device_id}' se encendió {enc_str} y se apagó {apag_str}."

