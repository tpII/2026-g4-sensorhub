#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#include "system_mgr.h"
#include "wifi_mgr.h"
#include "time_mgr.h"
#include "mqtt_mgr.h"
#include "sensor_service.h"

static const char *TAG = "MAIN";

void app_main(void) {
    ESP_LOGI(TAG, "Iniciando SensorHub...");

    // 1. Inicializa almacenamiento NVS e identidad del dispositivo (MAC y topicos)
    ESP_ERROR_CHECK(system_init());

    // 2. Inicializa y conecta el cliente WiFi
    ESP_LOGI(TAG, "Conectando a red WiFi...");
    ESP_ERROR_CHECK(wifi_mgr_init());
    // Si no hay IP en 1 minuto, el ESP_ERROR_CHECK reinicia el chip
    ESP_ERROR_CHECK(wifi_mgr_wait_connected(pdMS_TO_TICKS(60000)));

    // 3. Sincroniza la hora por SNTP para el campo "ts" de los payloads.
    // No es fatal: si vence el timeout se sigue sin "ts" (EMQX usa su propia hora) hasta que sincronice.
    ESP_LOGI(TAG, "Sincronizando hora (SNTP)...");
    time_mgr_init(pdMS_TO_TICKS(15000));

    // 4. Inicializa cliente MQTT con client_id unico (MAC del chip)
    ESP_LOGI(TAG, "Iniciando cliente MQTT...");
    ESP_ERROR_CHECK(mqtt_mgr_init(system_get_device_id()));
    ESP_ERROR_CHECK(mqtt_mgr_wait_connected(pdMS_TO_TICKS(10000)));

    // 5. Despacha e inicia el servicio correspondiente al tipo de dispositivo
    ESP_LOGI(TAG, "Iniciando servicio del dispositivo...");
    ESP_ERROR_CHECK(sensor_service_start());
}
