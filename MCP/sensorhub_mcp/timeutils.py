"""Normalización de instantes de tiempo para las tools que aceptan fechas como
argumento. El parseo de ISO 8601 lo hace el SDK de MCP (pydantic) a partir del
tipo `datetime` de los parámetros; acá solo se fija la zona horaria y se da
formato al literal RFC 3339 que espera Flux."""

from datetime import datetime, timezone


def as_utc(moment: datetime) -> datetime:
    """Interpreta una fecha sin zona horaria como UTC y convierte el resto a UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def to_flux_time(moment: datetime) -> str:
    return as_utc(moment).strftime("%Y-%m-%dT%H:%M:%SZ")
