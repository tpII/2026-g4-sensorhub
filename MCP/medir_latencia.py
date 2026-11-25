# Uso: python3 medir_latencia.py http://localhost:8000/mcp
#      python3 medir_latencia.py https://sensorhub.tailf54415.ts.net/mcp
import os, sys, time, json, urllib.request
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

URL = sys.argv[1]
N = 15
DHT = "111111111111"
PIR = "bbbbbbbbbbbb"
SW = "888888888888"
load_dotenv()
TOKEN = os.getenv("MCP_AUTH_TOKEN")

ahora = datetime.now(timezone.utc)
NOW = ahora.strftime("%Y-%m-%dT%H:%M:%SZ")
H1 = (ahora - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
H6 = (ahora - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")

headers = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

def post(body):
    r = urllib.request.urlopen(urllib.request.Request(URL, json.dumps(body).encode(), headers))
    r.read()
    return r

r = post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "latencia", "version": "1"}}})
headers["Mcp-Session-Id"] = r.headers["Mcp-Session-Id"]

def medir(tool, args, n=N):
    mn = 999999; mx = 0; suma = 0
    for i in range(n):
        if tool == "set_switch_state":
            args["state"] = "on" if i % 2 == 0 else "off"
        t = time.perf_counter()
        post({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}})
        ms = (time.perf_counter() - t) * 1000
        if ms < mn: mn = ms
        if ms > mx: mx = ms
        suma = suma + ms
    print(tool, "min", round(mn), "max", round(mx), "promedio", round(suma / n))

medir("resolve_device_id", {"description": "demo", "device_type": "dht"})
medir("get_current_climate", {"device_id": DHT})
medir("get_climate_at", {"device_id": DHT, "timestamp": H1})
medir("get_climate_trend", {"device_id": DHT, "start": H1, "end": NOW})
medir("get_last_motion_event", {"device_id": PIR})
medir("had_motion_in_range", {"device_id": PIR, "start": H6, "end": NOW})
medir("count_motion_events", {"device_id": PIR, "start": H6, "end": NOW})
medir("get_switch_state", {"device_id": SW})
medir("get_switch_on_duration", {"device_id": SW, "start": H6, "end": NOW})
medir("count_switch_toggles", {"device_id": SW, "start": H6, "end": NOW})
medir("set_switch_state", {"device_id": SW}, 6)  # mueve el switch real
