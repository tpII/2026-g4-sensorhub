"""Instancia compartida de FastMCP — los módulos de tools importan `mcp` de
acá para registrar sus funciones con @mcp.tool()."""

from mcp.server.fastmcp import FastMCP

from .config import MCP_HOST, MCP_HTTP_PATH, MCP_PORT

mcp = FastMCP("SensorHub", host=MCP_HOST, port=MCP_PORT)
mcp.settings.streamable_http_path = MCP_HTTP_PATH
