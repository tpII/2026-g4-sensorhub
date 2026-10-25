#ifndef TIME_MGR_H
#define TIME_MGR_H

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "freertos/FreeRTOS.h"

// Arranca SNTP (requiere WiFi con IP) y espera la primera sincronizacion o el timeout.
// SNTP sigue corriendo en segundo plano: si vence el timeout, la hora se sincroniza mas tarde.
esp_err_t time_mgr_init(TickType_t timeout_ticks);

// Retorna true si el reloj ya fue sincronizado por SNTP
bool time_mgr_is_synced(void);

// Retorna la hora actual en epoch de milisegundos, o 0 si el reloj aun no esta sincronizado
int64_t time_mgr_now_ms(void);

#endif // TIME_MGR_H
