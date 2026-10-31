#ifndef APP_CONFIG_H
#define APP_CONFIG_H

#include "sdkconfig.h"
#include "driver/gpio.h"

// =============================================================================
// Configuración General de la Aplicación y Conectividad (Agnóstica del Hardware)
// =============================================================================

// --- Credenciales WiFi ---
#define CONFIG_WIFI_SSID                "<ssid>"
#define CONFIG_WIFI_PASS                "<passwd>"

// Limite de potencia de transmision WiFi, en unidades de 0,25 dBm (rango 8..84; ej: 44 = 11 dBm, 34 = 8,5 dBm).
// 0 = sin limite (maximo del chip, ~20 dBm). Algunas placas ESP32-C3 SuperMini clon no logran
// autenticar con la potencia maxima (log "reason=2", AUTH_EXPIRE): bajarla suele resolverlo.
#define CONFIG_WIFI_MAX_TX_POWER        60

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

// Credenciales MQTT: el broker rechaza clientes sin usuario. Son las mismas para
// todos los dispositivos: MQTT_ESP_USERNAME / MQTT_ESP_PASSWORD de Stack/.env
#define CONFIG_MQTT_USERNAME            "esp"
#define CONFIG_MQTT_PASSWORD            "<mqtt_esp_password>"

// --- LED de estado (sin WiFi: parpadeo cada 1 s; al conectar: 3 parpadeos; actividad MQTT: destello) ---
// Pin y nivel activo del LED integrado de cada placa. GPIO_NUM_NC deshabilita el LED de estado.
// Las placas de S2, S3, C6 y H2 traen un LED RGB direccionable (WS2812), que no se maneja con un GPIO
// simple: ahi queda deshabilitado; para usarlo, conectar un LED comun y poner su pin aca.
// Si el pin coincide con CONFIG_SWITCH_PIN, en los nodos switch el LED de estado se deshabilita solo.
#if defined(CONFIG_IDF_TARGET_ESP32C3)
    #define CONFIG_STATUS_LED_PIN           GPIO_NUM_8    // LED azul integrado del ESP32-C3 SuperMini
    #define CONFIG_STATUS_LED_ACTIVE_LEVEL  0             // Enciende en bajo
#elif defined(CONFIG_IDF_TARGET_ESP32)
    #define CONFIG_STATUS_LED_PIN           GPIO_NUM_2    // LED azul integrado del ESP32 DevKit
    #define CONFIG_STATUS_LED_ACTIVE_LEVEL  1             // Enciende en alto
#else
    #define CONFIG_STATUS_LED_PIN           GPIO_NUM_NC
    #define CONFIG_STATUS_LED_ACTIVE_LEVEL  1
#endif

#endif // APP_CONFIG_H
