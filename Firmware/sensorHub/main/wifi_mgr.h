#ifndef WIFI_MGR_H
#define WIFI_MGR_H

#include "esp_err.h"
#include "freertos/FreeRTOS.h"

// Inicializa la pila de red y el driver WiFi (sin arrancarlo). Las credenciales las guarda el
// driver en NVS (las carga el provisioning, ver prov_mgr.h).
esp_err_t wifi_mgr_init(void);

// Arranca el modo STA y conecta con las credenciales guardadas, con auto-reconexion
esp_err_t wifi_mgr_connect(void);

// Bloquea hasta que el WiFi este conectado y con IP asignada o expire el timeout
esp_err_t wifi_mgr_wait_connected(TickType_t timeout_ticks);

// Borra las credenciales guardadas: en el proximo arranque se vuelve al provisioning
esp_err_t wifi_mgr_erase_credentials(void);

// Aplica el limite de potencia de TX de app_config.h (llamar despues de esp_wifi_start)
void wifi_mgr_apply_tx_power(void);

#endif // WIFI_MGR_H
