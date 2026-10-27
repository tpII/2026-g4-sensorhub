#include "sensor_service.h"
#include "system_mgr.h"
#include "devices/dht_device.h"
#include "devices/pir_device.h"
#include "devices/switch_device.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "SENSOR_SERVICE";

esp_err_t sensor_service_start(void) {
    const char *dtype = system_get_device_type();
    ESP_LOGI(TAG, "Despachando servicio para tipo de dispositivo: [%s]", dtype);

    if (strcmp(dtype, "dht") == 0) {
        return dht_device_start();

    } else if (strcmp(dtype, "pir") == 0) {
        return pir_device_start();

    } else if (strcmp(dtype, "switch") == 0) {
        return switch_device_start();
    }

    ESP_LOGE(TAG, "Tipo de dispositivo no soportado: [%s]", dtype);
    return ESP_ERR_NOT_SUPPORTED;
}

