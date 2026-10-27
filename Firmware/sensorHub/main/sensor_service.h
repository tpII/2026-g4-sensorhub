#ifndef SENSOR_SERVICE_H
#define SENSOR_SERVICE_H

#include "esp_err.h"

// Despacha e inicia el servicio correspondiente segun CONFIG_DEVICE_TYPE
esp_err_t sensor_service_start(void);

#endif // SENSOR_SERVICE_H

