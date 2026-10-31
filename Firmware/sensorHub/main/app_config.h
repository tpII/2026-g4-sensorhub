#ifndef APP_CONFIG_H
#define APP_CONFIG_H

#include "sdkconfig.h"
#include "driver/gpio.h"

// =============================================================================
// Configuración General de la Aplicación y Conectividad (Agnóstica del Hardware)
// =============================================================================

// --- Credenciales (WiFi y contraseña MQTT) ---
// Viven en secrets.h, ignorado por Git: copiar secrets.h.example y completarlo.
#if __has_include("secrets.h")
    #include "secrets.h"
#else
    #error "Falta main/secrets.h: copiar main/secrets.h.example a main/secrets.h y completar las credenciales"
#endif

// Limite de potencia de transmision WiFi, en unidades de 0,25 dBm (rango 8..84; ej: 44 = 11 dBm, 34 = 8,5 dBm).
// 0 = sin limite (maximo del chip, ~20 dBm). Algunas placas ESP32-C3 SuperMini clon no logran
// autenticar con la potencia maxima (log "reason=2", AUTH_EXPIRE): bajarla suele resolverlo.
#define CONFIG_WIFI_MAX_TX_POWER        60

// --- Selección de Protocolo MQTT ---
#define PROTOCOL_MQTT                   0   // TCP: mqtt://host:1883
#define PROTOCOL_MQTTS                  1   // SSL/TLS: mqtts://host:443 (acceso público: Traefik termina el TLS)
#define PROTOCOL_WS                     2   // WebSocket: ws://host:8083/mqtt
#define PROTOCOL_WSS                    3   // WebSocket Seguro: wss://host:8084/mqtt

// Modificar aquí el protocolo deseado:
#define CONFIG_SELECTED_PROTOCOL        PROTOCOL_MQTTS

// --- Sincronizacion horaria (SNTP) para el campo "ts" de los payloads ---
#define CONFIG_NTP_SERVER               "pool.ntp.org"

// --- Broker MQTT & Endpoints ---
// Dominio público del broker (registro A en Cloudflare). Con MQTTS tiene que ser
// el dominio y no una IP: el certificado y el ruteo por SNI dependen del nombre.
// Para conectarse directo al broker en la LAN (MQTT sin TLS), usar su IP local.
#define CONFIG_BROKER_HOST              "mqtt.sensorhub.wgr.com.ar"
#define CONFIG_WS_PATH                  "/mqtt"

#if (CONFIG_SELECTED_PROTOCOL == PROTOCOL_MQTT)
    #define CONFIG_BROKER_URI           "mqtt://" CONFIG_BROKER_HOST ":1883"
#elif (CONFIG_SELECTED_PROTOCOL == PROTOCOL_MQTTS)
    #define CONFIG_BROKER_URI           "mqtts://" CONFIG_BROKER_HOST ":443"
#elif (CONFIG_SELECTED_PROTOCOL == PROTOCOL_WS)
    #define CONFIG_BROKER_URI           "ws://" CONFIG_BROKER_HOST ":8083" CONFIG_WS_PATH
#elif (CONFIG_SELECTED_PROTOCOL == PROTOCOL_WSS)
    #define CONFIG_BROKER_URI           "wss://" CONFIG_BROKER_HOST ":8084" CONFIG_WS_PATH
#endif

// --- Jerarquía de Tópicos y Tipo de Dispositivo ---
#define CONFIG_MQTT_TOPIC_PREFIX        "sensorhub"

// Tipo a compilar ("dht", "pir", "switch", etc.): no tiene valor por defecto, lo
// define el build vía -DDEVICE_TYPE=... o la variable de entorno DEVICE_TYPE
// (ver main/CMakeLists.txt)
#ifndef CONFIG_DEVICE_TYPE
    #error "Falta DEVICE_TYPE: compilar con idf.py -DDEVICE_TYPE=<dht|pir|switch> build (o la variable de entorno DEVICE_TYPE)"
#endif

// Usuario MQTT: el broker rechaza clientes sin usuario. Es el mismo para todos
// los dispositivos: MQTT_ESP_USERNAME de Stack/.env (la contraseña está en secrets.h)
#define CONFIG_MQTT_USERNAME            "esp"

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
