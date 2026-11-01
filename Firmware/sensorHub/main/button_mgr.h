#ifndef BUTTON_MGR_H
#define BUTTON_MGR_H

#include "esp_err.h"

// Inicializa el boton de reset de WiFi (pin, nivel y tiempo en app_config.h).
// Mientras se mantiene presionado el LED queda en modo INICIANDO (1 parpadeo por segundo);
// al cumplir el tiempo borra las credenciales WiFi, muestra EXITO y reinicia en modo provisioning.
// Soltarlo antes cancela. Requiere NVS inicializado (system_init).
esp_err_t button_mgr_init(void);

#endif // BUTTON_MGR_H
