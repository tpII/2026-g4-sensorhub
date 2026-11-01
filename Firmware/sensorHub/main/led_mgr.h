#ifndef LED_MGR_H
#define LED_MGR_H

#include "esp_err.h"

// Modos del LED de estado (tiempos en app_config.h, CONFIG_LED_*)
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
