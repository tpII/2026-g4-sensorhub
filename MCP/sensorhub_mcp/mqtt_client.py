"""Cliente MQTT: lectura de mensajes retenidos y envío de comandos con
confirmación síncrona en telemetría."""

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Optional

import paho.mqtt.client as mqtt

from .config import MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_PASSWORD, MQTT_USERNAME

logger = logging.getLogger(__name__)

# Cuánto esperar la entrega del mensaje retenido al suscribirse antes de
# asumir que no hay nada publicado todavía en ese tópico y caer a InfluxDB.
MQTT_SUBSCRIBE_TIMEOUT_SECONDS = 2.0

# Cuánto esperar la confirmación física en `telemetry` tras publicar una orden
# en `command` (Escenario B, wiki 01 y 03 sección 6).
MQTT_COMMAND_TIMEOUT_SECONDS = 3.0


class MqttBrokerError(Exception):
    """Falla de conexión o publicación contra el broker MQTT."""


def get_mqtt_client(client_id: str = "mcp_client") -> mqtt.Client:
    client = mqtt.Client(client_id=client_id)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    return client


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


# Camino de Comando (wiki 01 Escenario B, wiki 03 secciones 3 y 6, wiki 05 sección 2):
# 1. Conecta y se suscribe primero a `telemetry_topic`, esperando SUBACK antes de
#    publicar el comando para no perder una respuesta rápida del actuador.
# 2. Ignora cualquier mensaje con `msg.retain == 1`: según MQTT 3.1.1 [MQTT-3.3.1-8/9],
#    el broker envía el mensaje retenido previo con RETAIN=1 al suscribirse, mientras
#    que toda confirmación emitida en vivo después de establecida la suscripción
#    llega con RETAIN=0 (aunque el actuador publique con retain=true). Así nunca se
#    confunde un estado viejo retenido de un dispositivo apagado con un acuse real.
# 3. Publica la orden en `command_topic` (QoS 1, retain=false) y espera la
#    confirmación física con `expected_field == expected_value` hasta `timeout`.
def publish_command_and_wait_feedback(
    command_topic: str,
    telemetry_topic: str,
    command_payload: dict[str, Any],
    expected_field: str,
    expected_value: Any,
    timeout: float = MQTT_COMMAND_TIMEOUT_SECONDS,
) -> Optional[dict[str, Any]]:
    subscribed = threading.Event()
    confirmed = threading.Event()
    connect_error: dict[str, Optional[int]] = {"rc": None}
    result: dict[str, Optional[dict[str, Any]]] = {"payload": None}

    def on_connect(client, _userdata, _flags, rc):
        if rc == 0:
            client.subscribe(telemetry_topic, qos=1)
        else:
            connect_error["rc"] = rc
            subscribed.set()
            confirmed.set()

    def on_subscribe(_client, _userdata, _mid, _granted_qos):
        subscribed.set()

    def on_message(_client, _userdata, msg):
        if msg.retain:
            return
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if isinstance(payload, dict) and payload.get(expected_field) == expected_value:
            result["payload"] = payload
            confirmed.set()

    client = get_mqtt_client(client_id=f"mcp_cmd_{os.getpid()}_{uuid.uuid4().hex[:8]}")
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    try:
        client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=10)
    except Exception as e:
        logger.error("No se pudo conectar al broker MQTT para enviar comando: %s", e)
        raise MqttBrokerError("No se pudo conectar al broker MQTT.") from e

    client.loop_start()
    try:
        deadline = time.monotonic() + timeout
        if not subscribed.wait(timeout=min(2.0, timeout)):
            raise MqttBrokerError("El broker MQTT no confirmó la suscripción al canal de telemetría.")
        if connect_error["rc"] is not None:
            raise MqttBrokerError(f"El broker MQTT rechazó la conexión (rc={connect_error['rc']}).")

        info = client.publish(command_topic, json.dumps(command_payload), qos=1, retain=False)
        pub_timeout = max(0.1, deadline - time.monotonic())
        info.wait_for_publish(timeout=pub_timeout)
        if not info.is_published():
            raise MqttBrokerError("No se pudo publicar el comando en el broker MQTT.")

        wait_remaining = max(0.0, deadline - time.monotonic())
        confirmed.wait(timeout=wait_remaining)
        return result["payload"]
    finally:
        client.loop_stop()
        try:
            client.disconnect()
        except Exception:
            pass
