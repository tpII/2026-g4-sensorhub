"""Cliente MQTT y lectura de mensajes retenidos."""

import json
import logging
import os
import threading
from typing import Optional

import paho.mqtt.client as mqtt

from .config import MQTT_BROKER_HOST, MQTT_BROKER_PORT

logger = logging.getLogger(__name__)

# Cuánto esperar la entrega del mensaje retenido al suscribirse antes de
# asumir que no hay nada publicado todavía en ese tópico y caer a InfluxDB.
MQTT_SUBSCRIBE_TIMEOUT_SECONDS = 2.0


def get_mqtt_client(client_id: str = "mcp_client") -> mqtt.Client:
    return mqtt.Client(client_id=client_id)


# Función síncrona y bloqueante (espera hasta `timeout`): las tools la
# ejecutan en un hilo aparte para no bloquear el servidor.
# Lee el mensaje retenido de un tópico suscribiéndose en el momento de la
# llamada, en vez de mantener una suscripción/caché de fondo. Como el
# tópico tiene retain=true, el broker entrega el mensaje retenido (si hay
# uno) de forma prácticamente inmediata al suscribirse — no es una espera
# indefinida, así que no hace falta cachear nada entre llamadas (ver wiki,
# 06, sección 1.3). El timeout solo cubre el caso de que el dispositivo
# nunca haya publicado nada en ese tópico.
def fetch_mqtt_retained(topic: str, timeout: float = MQTT_SUBSCRIBE_TIMEOUT_SECONDS) -> Optional[dict]:
    received = threading.Event()
    result = {"payload": None}

    def on_message(_client, _userdata, msg):
        try:
            result["payload"] = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        received.set()

    client = get_mqtt_client(client_id=f"mcp_read_{os.getpid()}_{threading.get_ident()}")
    client.on_message = on_message
    try:
        client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=10)
    except Exception as e:
        logger.warning("No se pudo conectar al broker MQTT: %s", e)
        return None

    client.loop_start()
    client.subscribe(topic, qos=1)
    received.wait(timeout)
    client.loop_stop()
    try:
        client.disconnect()
    except Exception:
        pass
    return result["payload"]
