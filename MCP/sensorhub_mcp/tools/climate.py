"""Tools de clima (DHT: temperatura y humedad) — ver wiki, 06, sección 3.1."""

import time
from datetime import datetime, timedelta, timezone

from ..devices import is_safe_device_id
from ..influx_client import query_field_aggregate, query_latest_climate
from ..mcp_app import mcp
from ..mqtt_client import fetch_mqtt_retained
from ..timeutils import parse_iso8601, to_flux_time

# Cuán viejo puede ser el `ts` de un mensaje retenido por MQTT antes de
# avisar explícitamente que puede no reflejar el estado actual del
# dispositivo (no es un TTL de caché — retain nunca expira solo, así que
# esto es lo único que distingue "el dispositivo recién publicó esto" de
# "esto es lo último que se supo de él, puede estar desconectado hace
# rato" — ver la discusión sobre el DHT apagado hace horas, wiki 03 sección 6).
MQTT_STALE_AFTER_SECONDS = 30

# Ventana hacia atrás para buscar la lectura vigente en un timestamp pedido
# (get_climate_at) — el DHT publica cada pocos segundos, así que alcanza
# con una ventana chica; si no hay nada en ese rango, se informa en vez de
# devolver un dato de hace demasiado tiempo.
CLIMATE_AT_WINDOW_HOURS = 2


@mcp.tool()
def get_current_climate(device_id: str) -> str:
    """
    Obtiene la temperatura y la humedad actuales de un sensor DHT, con la
    hora de la lectura. Llamar primero a resolve_device_id si el usuario no
    dio el device_id exacto.

    Args:
        device_id: Identificador exacto del sensor DHT (resuelto previamente
            con resolve_device_id si hace falta).
    """
    if not is_safe_device_id(device_id):
        return "El device_id no tiene un formato válido."

    retained = fetch_mqtt_retained(f"sensorhub/dht/{device_id}/telemetry")
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

    try:
        temp_val, hum_val, time_str = query_latest_climate(device_id)
    except Exception as e:
        print(f"[get_current_climate] Error consultando InfluxDB: {e}")
        return "No se pudo consultar el dato en este momento, intentá de nuevo en unos segundos."

    if temp_val is None and hum_val is None:
        return f"No se encontraron lecturas de clima en las últimas 24h para el sensor '{device_id}'."

    partes = []
    if temp_val is not None:
        partes.append(f"la temperatura es {float(temp_val):.1f}°C")
    if hum_val is not None:
        partes.append(f"la humedad es {float(hum_val):.1f}%")
    return f"Para el sensor '{device_id}', " + " y ".join(partes) + f" (registradas a las {time_str})."


@mcp.tool()
def get_climate_at(device_id: str, timestamp: str) -> str:
    """
    Obtiene la temperatura y humedad que estaban vigentes en un momento
    puntual del pasado, buscando la última lectura registrada hasta ese
    instante. Llamar primero a resolve_device_id si el usuario no dio el
    device_id exacto.

    Args:
        device_id: Identificador exacto del sensor DHT.
        timestamp: Instante consultado, en formato ISO 8601 (por ejemplo
            '2026-10-02T15:00:00Z'). Si el usuario dio una hora en lenguaje
            natural, convertirla a este formato antes de llamar a la tool.
    """
    if not is_safe_device_id(device_id):
        return "El device_id no tiene un formato válido."

    try:
        moment = parse_iso8601(timestamp)
    except ValueError:
        return f"No pude interpretar '{timestamp}' como una fecha/hora válida (formato esperado: ISO 8601)."

    start_rfc3339 = to_flux_time(moment - timedelta(hours=CLIMATE_AT_WINDOW_HOURS))
    stop_rfc3339 = to_flux_time(moment + timedelta(seconds=1))

    try:
        temp_val, temp_time = query_field_aggregate(
            "dht_telemetry", "temperature", device_id, "last", start_rfc3339, stop_rfc3339
        )
        hum_val, hum_time = query_field_aggregate(
            "dht_telemetry", "humidity", device_id, "last", start_rfc3339, stop_rfc3339
        )
    except Exception as e:
        print(f"[get_climate_at] Error consultando InfluxDB: {e}")
        return "No se pudo consultar el dato en este momento, intentá de nuevo en unos segundos."

    if temp_val is None and hum_val is None:
        return (
            f"No encontré lecturas del sensor '{device_id}' en las {CLIMATE_AT_WINDOW_HOURS}h "
            f"previas a {timestamp}."
        )

    partes = []
    if temp_val is not None:
        partes.append(f"la temperatura era {float(temp_val):.1f}°C (registrada a las {temp_time})")
    if hum_val is not None:
        partes.append(f"la humedad era {float(hum_val):.1f}% (registrada a las {hum_time})")
    return f"Para el sensor '{device_id}', " + " y ".join(partes) + "."


@mcp.tool()
def get_climate_trend(device_id: str, start: str, end: str) -> str:
    """
    Resume cómo varió la temperatura y la humedad de un sensor DHT entre dos
    instantes (mínimo, máximo y promedio) — no devuelve la serie completa,
    sino un resumen en lenguaje natural de la tendencia. Llamar primero a
    resolve_device_id si el usuario no dio el device_id exacto.

    Args:
        device_id: Identificador exacto del sensor DHT.
        start: Inicio del rango, en formato ISO 8601 (ej. '2026-10-02T10:00:00Z').
        end: Fin del rango, en formato ISO 8601 (ej. '2026-10-02T18:00:00Z').
    """
    if not is_safe_device_id(device_id):
        return "El device_id no tiene un formato válido."

    try:
        start_dt = parse_iso8601(start)
        end_dt = parse_iso8601(end)
    except ValueError:
        return f"No pude interpretar el rango '{start}' a '{end}' como fechas válidas (formato esperado: ISO 8601)."

    if start_dt >= end_dt:
        return "El inicio del rango tiene que ser anterior al fin."

    start_rfc3339 = to_flux_time(start_dt)
    stop_rfc3339 = to_flux_time(end_dt)

    try:
        temp_min, _ = query_field_aggregate("dht_telemetry", "temperature", device_id, "min", start_rfc3339, stop_rfc3339)
        temp_max, _ = query_field_aggregate("dht_telemetry", "temperature", device_id, "max", start_rfc3339, stop_rfc3339)
        temp_mean, _ = query_field_aggregate("dht_telemetry", "temperature", device_id, "mean", start_rfc3339, stop_rfc3339)
        hum_min, _ = query_field_aggregate("dht_telemetry", "humidity", device_id, "min", start_rfc3339, stop_rfc3339)
        hum_max, _ = query_field_aggregate("dht_telemetry", "humidity", device_id, "max", start_rfc3339, stop_rfc3339)
        hum_mean, _ = query_field_aggregate("dht_telemetry", "humidity", device_id, "mean", start_rfc3339, stop_rfc3339)
    except Exception as e:
        print(f"[get_climate_trend] Error consultando InfluxDB: {e}")
        return "No se pudo consultar el dato en este momento, intentá de nuevo en unos segundos."

    if temp_mean is None and hum_mean is None:
        return f"No encontré lecturas del sensor '{device_id}' entre {start} y {end}."

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
    return f"Entre {start} y {end}, para el sensor '{device_id}', " + "; y ".join(partes) + "."
