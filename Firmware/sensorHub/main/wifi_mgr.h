#ifndef WIFI_MGR_H
#define WIFI_MGR_H

#include "esp_err.h"
#include "freertos/FreeRTOS.h"

// Inicializa y conecta el cliente WiFi en modo STA
esp_err_t wifi_mgr_init(void);

// Bloquea hasta que el WiFi este conectado y con IP asignada o expire el timeout
esp_err_t wifi_mgr_wait_connected(TickType_t timeout_ticks);

#endif // WIFI_MGR_H

