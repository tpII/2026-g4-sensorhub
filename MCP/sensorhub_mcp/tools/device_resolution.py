"""Tool de resolución de device_id a partir de una descripción en lenguaje
libre — ver wiki, 06, secciones 2.3 a 2.5."""

from typing import Annotated, Any, Literal, Optional

from mcp.server.mcpserver import AcceptedElicitation, Context, Elicit, ElicitationResult, Resolve
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field, create_model

from ..devices import load_device_registry, match_device_candidates
from ..mcp_app import mcp
from .common import DeviceType, read_only, run_blocking

DescriptionParam = Annotated[
    str,
    Field(
        description=(
            "Cómo se refirió el usuario al dispositivo: solo el nombre del lugar o el apodo "
            "(por ejemplo 'cocina', no 'el sensor de la cocina'). No necesita coincidir exacto "
            "con el nombre registrado."
        ),
        min_length=1,
        max_length=100,
    ),
]

DeviceTypeParam = Annotated[
    Optional[DeviceType],
    Field(
        description=(
            "Tipo de dispositivo si se puede inferir de la pregunta: dht (temperatura y humedad), "
            "pir (movimiento o presencia) o switch (relé o luz). Ayuda a desambiguar cuando el "
            "mismo nombre está registrado para más de un tipo."
        )
    ),
]


def _options(registry: list[dict]) -> dict[str, str]:
    """Opción visible para el usuario -> device_id. El tipo se agrega solo si el
    nombre amigable se repite entre tipos."""
    names = [r["friendly_name"] for r in registry]
    return {
        (r["friendly_name"] if names.count(r["friendly_name"]) == 1 else f"{r['friendly_name']} ({r['device_type']})"): r["device_id"]
        for r in registry
    }


def _supports_elicitation(ctx: Context) -> bool:
    caps = ctx.client_capabilities
    elicitation = caps.elicitation if caps is not None else None
    # Un `elicitation: {}` sin modos (forma previa a los modos) cuenta como formulario.
    return elicitation is not None and (elicitation.form is not None or elicitation.url is None)


NONE_OF_THESE = "Ninguno de estos"


async def _resolve_description(description: str, device_type: Optional[str], ctx: Context) -> Any:
    """Resolver (SDK v2): se ejecuta antes que la tool. Devuelve el device_id si la
    descripción coincide con un único dispositivo registrado; si no coincide con
    ninguno o con varios, y el cliente soporta elicitation, devuelve un pedido
    `Elicit` para que el usuario elija (entre los candidatos, o entre todos los
    registrados si no hubo ninguno). El SDK elige el transporte según el protocolo
    negociado: en 2026-07-28 lo envía como InputRequiredResult (multi round-trip)
    y en revisiones anteriores, como solicitud elicitation/create durante la llamada."""
    registry = await run_blocking(load_device_registry, device_type)
    if not registry:
        raise ToolError("No hay dispositivos registrados para esa búsqueda.")
    candidates = match_device_candidates(description, registry)
    if len(candidates) == 1 or not _supports_elicitation(ctx):
        return candidates[0]["device_id"] if len(candidates) == 1 else None

    if candidates:
        options = _options(candidates)
        prompt = (
            f"«{description}» coincide con más de un dispositivo. Elegir a cuál se refiere, "
            f"o «{NONE_OF_THESE}» para volver a indicar el nombre o el device_id exacto:"
        )
    else:
        options = _options(registry)
        prompt = f"No se identificó el dispositivo «{description}». Elegir a cuál de los registrados se refiere:"
    options = {**options, NONE_OF_THESE: ""}
    # Esquema de elicitation: un único campo con los nombres registrados como enum.
    choice = create_model(
        "DeviceChoice",
        dispositivo=(Literal[tuple(options)], Field(description="Dispositivo registrado")),
    )
    return Elicit(prompt, choice)


@mcp.tool(annotations=read_only("Resolver dispositivo por nombre"))
async def resolve_device_id(
    description: DescriptionParam,
    resolution: Annotated[ElicitationResult[Any], Resolve(_resolve_description)],
    device_type: DeviceTypeParam = None,
) -> str:
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
    ninguna coincidencia razonable, devuelve un error en vez de adivinar el
    dispositivo más parecido. Si la descripción coincide con varios, le pide
    al usuario que elija entre los mejores (hasta 4).
    """
    # `resolution` lo completa el resolver (no es un argumento del modelo): un
    # device_id encontrado, la elección del usuario, o un rechazo/cancelación.
    if isinstance(resolution, AcceptedElicitation):
        data = resolution.data
        if isinstance(data, str):
            return data
        if data is not None:
            registry = await run_blocking(load_device_registry, device_type)
            candidates = match_device_candidates(description, registry)
            chosen = _options(candidates or registry).get(data.dispositivo)
            if chosen:
                return chosen
    raise ToolError(
        f"No se identificó ningún dispositivo que coincida con '{description}'. "
        "Pedirle al usuario que confirme el nombre o el lugar del dispositivo."
    )
