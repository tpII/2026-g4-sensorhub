#include "system_mgr.h"
#include "app_config.h"
#include "nvs_flash.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_mac.h"
#include <stdio.h>

static const char *TAG = "SYSTEM_MGR";

static char s_device_id[16] = {0};
static char s_telemetry_topic[80] = {0};
static char s_command_topic[80] = {0};
static char s_status_topic[80] = {0};

esp_err_t system_init(void) {
    // 1. Inicializar almacenamiento no volatil NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "Borrando NVS flash por formato incompatible...");
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Fallo al inicializar NVS flash: %s", esp_err_to_name(ret));
        return ret;
    }

    // 2. Instalar el servicio global de ISR de GPIO (los devices solo agregan su handler por pin)
    ret = gpio_install_isr_service(0);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Fallo al instalar servicio ISR de GPIO: %s", esp_err_to_name(ret));
        return ret;
    }

    // 3. Resolver identidad unica del dispositivo (MAC WiFi STA en minusculas, sin separadores)
    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    snprintf(s_device_id, sizeof(s_device_id), "%02x%02x%02x%02x%02x%02x",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);

    // 4. Construir topicos normalizados
    // Formato: <prefix>/<device_type>/<device_id>/<action>
    // Ejemplos reales segun el tipo de dispositivo:
    //  - Telemetria DHT11: "sensorhub/dht/983dae529858/telemetry"
    //  - Telemetria PIR:   "sensorhub/pir/983dae529858/telemetry"
    //  - Comandos Switch:  "sensorhub/switch/983dae529858/command"
    //  - Feedback Switch:  "sensorhub/switch/983dae529858/telemetry"
    //  - Presencia LWT:    "sensorhub/switch/983dae529858/status"
    snprintf(s_telemetry_topic, sizeof(s_telemetry_topic), "%s/%s/%s/telemetry",
             CONFIG_MQTT_TOPIC_PREFIX, CONFIG_DEVICE_TYPE, s_device_id);

    snprintf(s_command_topic, sizeof(s_command_topic), "%s/%s/%s/command",
             CONFIG_MQTT_TOPIC_PREFIX, CONFIG_DEVICE_TYPE, s_device_id);

    snprintf(s_status_topic, sizeof(s_status_topic), "%s/%s/%s/status",
             CONFIG_MQTT_TOPIC_PREFIX, CONFIG_DEVICE_TYPE, s_device_id);

    ESP_LOGI(TAG, "Sistema inicializado. Device ID: [%s] | Tipo: [%s]", s_device_id, CONFIG_DEVICE_TYPE);
    ESP_LOGI(TAG, "Topico Telemetria: %s", s_telemetry_topic);
    ESP_LOGI(TAG, "Topico Comandos:   %s", s_command_topic);
    ESP_LOGI(TAG, "Topico Status LWT: %s", s_status_topic);

    return ESP_OK;
}

const char* system_get_device_id(void) {
    return s_device_id;
}

const char* system_get_device_type(void) {
    return CONFIG_DEVICE_TYPE;
}

const char* system_get_telemetry_topic(void) {
    return s_telemetry_topic;
}

const char* system_get_command_topic(void) {
    return s_command_topic;
}

const char* system_get_status_topic(void) {
    return s_status_topic;
}

