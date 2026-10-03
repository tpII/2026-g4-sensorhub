"""
Importar este paquete registra todas las tools (@mcp.tool() se ejecuta al
importar cada módulo). main.py hace `from . import tools` antes de
mcp.run() por este motivo — sin este import, ninguna tool quedaría
registrada aunque el código exista.

"""

from . import climate, device_resolution  # noqa: F401
