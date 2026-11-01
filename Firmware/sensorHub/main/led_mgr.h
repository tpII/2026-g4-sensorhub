#ifndef LED_MGR_H
#define LED_MGR_H

#include "esp_err.h"

// --- Tiempos (ms) de cada modo del LED ---
// El pin y el nivel activo dependen de la placa: estan en app_config.h (CONFIG_STATUS_LED_*).
//  INICIANDO:         parpadeo lento continuo (conectando al WiFi, boton de reset presionado)
//  ESPERANDO_ACCION:  parpadeo rapido continuo (provisioning BLE sin la app conectada)
//  EXITO:             pulsos muy rapidos y pasa a NORMAL (WiFi conectado, app conectada por BLE, credenciales borradas)
//  NORMAL:            apagado, con un destello corto por cada mensaje MQTT enviado o recibido
#define CONFIG_LED_INICIANDO_ON_MS          500
#define CONFIG_LED_INICIANDO_OFF_MS         500
#define CONFIG_LED_ESPERANDO_ACCION_ON_MS   250
#define CONFIG_LED_ESPERANDO_ACCION_OFF_MS  250
#define CONFIG_LED_EXITO_PULSES             3
#define CONFIG_LED_EXITO_ON_MS              150
#define CONFIG_LED_EXITO_OFF_MS             183
#define CONFIG_LED_NORMAL_ON_MS             50
// Duracion total del modo EXITO
#define CONFIG_LED_EXITO_DURATION_MS        (CONFIG_LED_EXITO_PULSES * (CONFIG_LED_EXITO_ON_MS + CONFIG_LED_EXITO_OFF_MS))

// Modos del LED de estado
typedef enum {
    LED_MODE_NORMAL,            // Apagado; destello corto por actividad MQTT
    LED_MODE_INICIANDO,         // Parpadeo lento continuo
    LED_MODE_ESPERANDO_ACCION,  // Parpadeo rapido continuo
    LED_MODE_EXITO,             // Pulsos muy rapidos; al terminar pasa solo a NORMAL
} led_mode_t;

// Inicializa el LED de estado (pin y nivel activo en app_config.h) y su tarea de parpadeo.
// Arranca en modo INICIANDO. Si el pin no esta definido o lo usa el actuador del switch,
// queda deshabilitado y las demas funciones no hacen nada.
esp_err_t led_mgr_init(void);

// Cambia el modo del LED. Pedir el modo en curso no reinicia el patron.
void led_mgr_set_mode(led_mode_t mode);

// Fuerza un modo por encima del que pidio el sistema (ej: boton de reset presionado) hasta
// llamar a led_mgr_clear_override(). Un override EXITO se libera solo al terminar los pulsos.
void led_mgr_set_override(led_mode_t mode);
void led_mgr_clear_override(void);

// Destello corto de actividad (mensaje MQTT enviado o recibido). Solo se ve en modo NORMAL.
void led_mgr_notify_activity(void);

#endif // LED_MGR_H
