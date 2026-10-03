"""Parseo y formateo de instantes de tiempo para las tools que aceptan
fechas/horas como argumento (ISO 8601 <-> literal RFC3339 de Flux)."""

from datetime import datetime, timezone


def parse_iso8601(value: str) -> datetime:
    """Acepta ISO 8601 con o sin sufijo 'Z'; devuelve un datetime en UTC."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_flux_time(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
