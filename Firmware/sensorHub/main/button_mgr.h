#ifndef BUTTON_MGR_H
#define BUTTON_MGR_H

#include <stdbool.h>
#include "esp_err.h"

// Inicializa el boton de reset de WiFi (pin, nivel y tiempo en app_config.h). Funciona por
// interrupcion: la tarea del boton solo se despierta al presionarlo.
// Mientras se mantiene presionado el LED queda en modo INICIANDO (1 parpadeo por segundo);
// al cumplir el tiempo borra las credenciales WiFi, muestra EXITO y reinicia en modo provisioning.
// Soltarlo antes cancela. Requiere system_init() (NVS y servicio de ISR de GPIO).
esp_err_t button_mgr_init(void);

// Indica si el boton esta presionado y midiendo el tiempo para borrar las credenciales.
// Quien vaya a reiniciar el chip por una falla debe esperar a que vuelva a false.
bool button_mgr_is_held(void);

#endif // BUTTON_MGR_H
