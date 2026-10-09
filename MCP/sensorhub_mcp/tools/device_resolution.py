"""Tool de resolución de device_id a partir de una descripción en lenguaje
libre — ver wiki, 06, sección 2.3."""

from typing import Optional

from ..devices import load_device_registry, match_device_id
from ..mcp_app import mcp


@mcp.tool()
def resolve_device_id(description: str, device_type: Optional[str] = None) -> str:
    """
    Traduce una descripción en lenguaje libre de un dispositivo (por ejemplo
    "cocina", "el de la oficina") al device_id exacto que esperan las demás
    tools. Llamarla ANTES de cualquier tool de lectura o de comando cuando el
    usuario nombró el dispositivo por un lugar o un apodo, y usar el valor que
    devuelve como argumento device_id de esa tool. Si el usuario ya dio el
    device_id (la MAC del dispositivo: 12 caracteres hexadecimales, con o sin
    ':'), no hace falta llamarla.

    Si encuentra una coincidencia, el valor devuelto es el device_id en sí
    (un identificador interno) — no corresponde mostrárselo al usuario tal
    cual, sino usarlo para completar la siguiente llamada. Si no encuentra
    ninguna coincidencia razonable, devuelve una explicación en lenguaje
    natural en vez de adivinar el dispositivo más parecido.

    Args:
        description: Cómo se refirió el usuario al dispositivo (un lugar,
            un apodo, lo que haya dicho) — no necesita coincidir exacto con
            el nombre registrado.
        device_type: Tipo de dispositivo si se puede inferir de la pregunta
            ("dht", "pir", "switch"). Opcional: ayuda a desambiguar cuando
            el mismo nombre está registrado para más de un tipo.
    """
    registry = load_device_registry(device_type)
    if not registry:
        return "No hay dispositivos registrados todavía para esa búsqueda."

    device_id = match_device_id(description, registry)
    if device_id is not None:
        return device_id
    return (
        f"No identifico ningún dispositivo que coincida con '{description}'. "
        "¿Podrías confirmar el nombre o el lugar del dispositivo?"
    )
