#ifndef APP_CONFIG_H
#define APP_CONFIG_H

#include "sdkconfig.h"

// =============================================================================
// Configuración General de la Aplicación y Conectividad (Agnóstica del Hardware)
// =============================================================================

// --- Credenciales WiFi ---
#define CONFIG_WIFI_SSID                "Andy2"
#define CONFIG_WIFI_PASS                "3CBBCEF573"

// --- Selección de Protocolo MQTT ---
#define PROTOCOL_MQTT                   0   // TCP: mqtt://host:1883
#define PROTOCOL_MQTTS                  1   // SSL/TLS: mqtts://host:8883
#define PROTOCOL_WS                     2   // WebSocket: ws://host:8083/mqtt
#define PROTOCOL_WSS                    3   // WebSocket Seguro: wss://host:8084/mqtt

// Modificar aquí el protocolo deseado:
#define CONFIG_SELECTED_PROTOCOL        PROTOCOL_MQTT

// --- Sincronizacion horaria (SNTP) para el campo "ts" de los payloads ---
#define CONFIG_NTP_SERVER               "pool.ntp.org"

// --- Broker MQTT & Endpoints ---
#define CONFIG_BROKER_HOST              "192.168.0.190"
#define CONFIG_WS_PATH                  "/mqtt"

#if (CONFIG_SELECTED_PROTOCOL == PROTOCOL_MQTT)
    #define CONFIG_BROKER_URI           "mqtt://" CONFIG_BROKER_HOST ":1883"
#elif (CONFIG_SELECTED_PROTOCOL == PROTOCOL_MQTTS)
    #define CONFIG_BROKER_URI           "mqtts://" CONFIG_BROKER_HOST ":8883"
#elif (CONFIG_SELECTED_PROTOCOL == PROTOCOL_WS)
    #define CONFIG_BROKER_URI           "ws://" CONFIG_BROKER_HOST ":8083" CONFIG_WS_PATH
#elif (CONFIG_SELECTED_PROTOCOL == PROTOCOL_WSS)
    #define CONFIG_BROKER_URI           "wss://" CONFIG_BROKER_HOST ":8084" CONFIG_WS_PATH
#endif

// --- Jerarquía de Tópicos y Tipo de Dispositivo ---
#define CONFIG_MQTT_TOPIC_PREFIX        "sensorhub"

// Tipo a compilar ("dht", "pir", "switch", etc.).
// Puede sobreescribirse desde el build vía -DDEVICE_TYPE=... o variable de entorno DEVICE_TYPE
#ifndef CONFIG_DEVICE_TYPE
    #define CONFIG_DEVICE_TYPE          "dht"
#endif

// Credenciales MQTT (opcionales)
#define CONFIG_MQTT_USERNAME            ""
#define CONFIG_MQTT_PASSWORD            ""

#endif // APP_CONFIG_H
