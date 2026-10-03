"""Identificación de dispositivos: registro de nombres amigables, validación
de device_id y normalización de descripciones en lenguaje libre.

Usado por la tool resolve_device_id y por cada tool de lectura/comando que
necesite validar un device_id antes de interpolarlo en una query."""

import csv
import difflib
import os
import re
from typing import Optional

# Registro de dispositivos (device_type, device_id, nombre amigable) para
# resolve_device_id. Se completa a mano por ahora (ver wiki, 06, sección 2.3)
# — a futuro podría poblarse vía un flujo de aprovisionamiento al registrar
# un dispositivo nuevo. Vive en la raíz de MCP/, junto a .env, no dentro del
# paquete.
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_MCP_ROOT_DIR = os.path.dirname(_PACKAGE_DIR)
DEVICE_REGISTRY_PATH = os.getenv("DEVICE_REGISTRY_PATH", os.path.join(_MCP_ROOT_DIR, "devices.csv"))

# Umbral de similitud para el fuzzy match de nombres amigables (0-1). El
# default de difflib (0.6) da falsos positivos entre palabras cortas en
# español que comparten muchas letras (p. ej. "cocina" vs "oficina" da 0.77
# de similitud) — con 0.8 ese caso se rechaza sin perder tolerancia a
# errores de tipeo reales ("livin"/"living" da 0.91). Ajustar si en la
# práctica resulta muy laxo o muy estricto — ver "Qué queda abierto" en la
# wiki, 06, sección 4.
DEVICE_MATCH_CUTOFF = 0.8

# Palabras sin valor para identificar un dispositivo (artículos/preposiciones
# sueltos) — se descartan antes de comparar, así "el de la oficina" compara
# contra "oficina" en vez de perder similitud por las palabras de relleno.
_DEVICE_DESCRIPTION_STOPWORDS = {"el", "la", "los", "las", "de", "del", "un", "una"}

# device_id siempre se interpola en una query Flux armada con f-strings —
# validar contra un patrón fijo antes de usarlo evita que un valor con
# comillas o sintaxis de Flux altere el filtro (ver wiki, 06, sección 1.3).
_SAFE_DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def is_safe_device_id(device_id: str) -> bool:
    return bool(_SAFE_DEVICE_ID_PATTERN.match(device_id))


# Nunca se le pasa entero al LLM (ver wiki, 06, sección 2.3) — solo lo usa
# resolve_device_id, server-side, para resolver una descripción puntual.
# device_type filtra el registro antes de devolverlo (p. ej. para
# desambiguar un nombre repetido entre tipos de dispositivo distintos).
def load_device_registry(device_type: Optional[str] = None) -> list[dict]:
    try:
        with open(DEVICE_REGISTRY_PATH, newline="", encoding="utf-8") as f:
            registry = list(csv.DictReader(f))
    except FileNotFoundError:
        return []
    if device_type:
        registry = [r for r in registry if r["device_type"] == device_type]
    return registry


def normalize_device_description(description: str) -> str:
    words = [
        w for w in re.split(r"\s+", description.strip().lower())
        if w not in _DEVICE_DESCRIPTION_STOPWORDS
    ]
    return " ".join(words) if words else description.strip().lower()


def match_device_id(description: str, registry: list[dict]) -> Optional[str]:
    """
    Resuelve una descripción en lenguaje libre a un device_id dentro de un
    registro ya cargado (y, si corresponde, ya filtrado por device_type),
    o devuelve None si no hay ninguna coincidencia razonable.
    """
    for entry in registry:
        if entry["device_id"] == description.strip():
            return entry["device_id"]

    friendly_names = [entry["friendly_name"] for entry in registry]
    matches = difflib.get_close_matches(
        normalize_device_description(description),
        [name.lower() for name in friendly_names],
        n=1,
        cutoff=DEVICE_MATCH_CUTOFF,
    )
    if not matches:
        return None

    matched_entry = next(
        entry for entry in registry if entry["friendly_name"].lower() == matches[0]
    )
    return matched_entry["device_id"]
