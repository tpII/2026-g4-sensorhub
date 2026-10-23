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
# de similitud). ratio() es 2*M/T (M = caracteres coincidentes, T = suma de
# los largos), así que una subcadena como "cina" vs "cocina" da 0.8. Con 0.7
# se aceptan descripciones truncadas o con typos, a costa de que varios
# nombres lo superen: en ese caso no se adivina, se le muestran al usuario los
# mejores (hasta DEVICE_MATCH_MAX_CANDIDATES) para que elija. Ajustar si en la
# práctica resulta muy laxo o muy estricto — ver "Qué queda abierto" en la
# wiki, 06, sección 4.
DEVICE_MATCH_CUTOFF = 0.7
DEVICE_MATCH_MAX_CANDIDATES = 4

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


# MAC escrita con separadores (98:3d:ae:52:98:58 o 98-3d-ae-52-98-58), ya en
# minúsculas. Los tópicos MQTT y los tags de InfluxDB distinguen mayúsculas, y
# el contrato fija el device_id en minúsculas y sin separadores (wiki, 03,
# sección 1) — por eso se lleva a esa forma antes de armar tópicos o queries.
_MAC_WITH_SEPARATORS_PATTERN = re.compile(r"^[0-9a-f]{2}([:-])[0-9a-f]{2}(\1[0-9a-f]{2}){4}$")


def canonical_device_id(device_id: str) -> str:
    """Lleva un device_id a la forma del contrato: minúsculas y, si es una
    MAC con separadores, sin ellos ("98:3D:AE:52:98:58" -> "983dae529858")."""
    text = device_id.strip().lower()
    if _MAC_WITH_SEPARATORS_PATTERN.match(text):
        text = text.replace(":", "").replace("-", "")
    return text


# Verificación de existencia que usan las tools de datos cuando reciben un
# device_id directo (sin pasar por resolve_device_id): distingue "no existe
# ese dispositivo" de "no hay datos" (ver wiki, 06, sección 2.3). Se valida
# contra el registro y no contra InfluxDB o el broker porque estos solo dicen
# si el dispositivo publicó alguna vez, no si está registrado.
def find_registered_device(device_id: str, device_type: Optional[str] = None) -> Optional[str]:
    canonical = canonical_device_id(device_id)
    for entry in load_device_registry(device_type):
        if entry["device_id"].lower() == canonical:
            return entry["device_id"]
    return None


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


def match_device_candidates(description: str, registry: list[dict]) -> list[dict]:
    """
    Devuelve las entradas del registro (ya cargado y, si corresponde, ya
    filtrado por device_type) que coinciden con una descripción en lenguaje
    libre, de mejor a peor: hasta DEVICE_MATCH_MAX_CANDIDATES con similitud >=
    DEVICE_MATCH_CUTOFF, desempatando por nombre amigable en orden alfabético.
    Lista vacía si ninguna alcanza el umbral. Una lista de un solo elemento es
    una coincidencia inequívoca; con más, la descripción es ambigua.
    """
    # Si la descripción ya es un device_id registrado (en cualquier forma:
    # mayúsculas, MAC con separadores), es inequívoca.
    canonical = canonical_device_id(description)
    for entry in registry:
        if entry["device_id"].lower() == canonical:
            return [entry]

    normalized = normalize_device_description(description)
    # Un nombre amigable exacto no es ambiguo con otros parecidos ("cocina" vs
    # "oficina"); solo lo es si el mismo nombre está registrado para más de un tipo.
    exact = [e for e in registry if e["friendly_name"].lower() == normalized]
    if exact:
        return exact[:DEVICE_MATCH_MAX_CANDIDATES]
    scored = []
    for entry in registry:
        name = entry["friendly_name"].lower()
        score = difflib.SequenceMatcher(None, normalized, name).ratio()
        if score >= DEVICE_MATCH_CUTOFF:
            scored.append((-score, name, entry))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [entry for _, _, entry in scored[:DEVICE_MATCH_MAX_CANDIDATES]]
