#ifndef LED_MGR_H
#define LED_MGR_H

#include <stdbool.h>
#include "esp_err.h"

// Inicializa el LED de estado (pin y nivel activo en app_config.h) y su tarea de parpadeo.
// Arranca en estado "sin WiFi" (parpadeo cada 1 s). Si el pin no esta definido o lo usa
// el actuador del switch, queda deshabilitado y las demas funciones no hacen nada.
esp_err_t led_mgr_init(void);

// Informa el estado del WiFi: desconectado -> parpadeo cada 1 s; al conectar -> 3 parpadeos (500 ms on / 1 s off) y apagado
void led_mgr_set_wifi_connected(bool connected);

// Parpadeo corto de actividad (mensaje MQTT enviado o recibido)
void led_mgr_notify_activity(void);

#endif // LED_MGR_H
