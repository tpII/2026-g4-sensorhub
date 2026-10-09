"""Tool de resolución de device_id a partir de una descripción en lenguaje
libre — ver wiki, 06, secciones 2.3 a 2.5."""

from typing import Annotated, Optional

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ClientCapabilities, ElicitationCapability
from pydantic import BaseModel, Field, create_model

from ..devices import load_device_registry, match_device_id
from ..mcp_app import mcp
from .common import DeviceType, log, read_only, run_blocking


@mcp.tool(annotations=read_only("Resolver dispositivo por nombre"))
async def resolve_device_id(
    description: Annotated[
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
    ],
    ctx: Context,
    device_type: Annotated[
        Optional[DeviceType],
        Field(
            description=(
                "Tipo de dispositivo si se puede inferir de la pregunta: dht (temperatura y humedad), "
                "pir (movimiento o presencia) o switch (relé o luz). Ayuda a desambiguar cuando el "
                "mismo nombre está registrado para más de un tipo."
            )
        ),
    ] = None,
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
    dispositivo más parecido.
    """
    registry = await run_blocking(load_device_registry, device_type)
    if not registry:
        raise ToolError("No hay dispositivos registrados para esa búsqueda.")

    device_id = match_device_id(description, registry)
    if device_id is not None:
        return device_id

    # Sin coincidencia: si el cliente soporta elicitation, se le pregunta al
    # usuario a cuál de los dispositivos registrados se refiere; si no (o si
    # el servidor corre en modo stateless, donde no se conocen las capacidades
    # del cliente), se informa el error para que el modelo le pregunte.
    chosen = await _ask_user(ctx, description, registry)
    if chosen is not None:
        return chosen
    raise ToolError(
        f"No se identificó ningún dispositivo que coincida con '{description}'. "
        "Pedirle al usuario que confirme el nombre o el lugar del dispositivo."
    )


async def _ask_user(ctx: Context, description: str, registry: list[dict]) -> Optional[str]:
    """Pide al usuario, mediante elicitation, que elija entre los dispositivos
    registrados. Devuelve el device_id elegido, o None si el cliente no soporta
    elicitation o el usuario no eligió ninguno."""
    supports = ctx.session.check_client_capability(ClientCapabilities(elicitation=ElicitationCapability()))
    if not supports:
        return None

    # Una opción por dispositivo; el tipo se agrega solo si el nombre se repite.
    names = [r["friendly_name"] for r in registry]
    options = {
        (r["friendly_name"] if names.count(r["friendly_name"]) == 1 else f"{r['friendly_name']} ({r['device_type']})"): r["device_id"]
        for r in registry
    }
    # Los esquemas de elicitation solo admiten campos primitivos: el campo es
    # un str y la lista de opciones se publica como enum en el esquema.
    Choice: type[BaseModel] = create_model(
        "DeviceChoice",
        dispositivo=(str, Field(description="Dispositivo registrado", json_schema_extra={"enum": list(options)})),
    )
    try:
        result = await ctx.elicit(
            message=f"No se identificó el dispositivo «{description}». Elegir a cuál de los registrados se refiere:",
            schema=Choice,
        )
    except Exception as e:
        await log(ctx, "warning", f"Elicitation no disponible: {e}")
        return None

    if result.action == "accept":
        return options.get(result.data.dispositivo)
    return None
