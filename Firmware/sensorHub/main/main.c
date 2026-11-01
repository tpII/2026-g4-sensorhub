#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_system.h"

#include "system_mgr.h"
#include "led_mgr.h"
#include "button_mgr.h"
#include "wifi_mgr.h"
#include "prov_mgr.h"
#include "time_mgr.h"
#include "mqtt_mgr.h"
#include "sensor_service.h"

static const char *TAG = "MAIN";

// Reinicia el chip ante una falla de conexion. Si el boton de reset esta presionado espera a que
// se resuelva: al cumplir el tiempo el boton borra las credenciales y reinicia el mismo; si se
// suelta antes, se hace este reinicio.
static void restart_on_failure(const char *reason) {
    ESP_LOGE(TAG, "%s. Reiniciando...", reason);
    while (button_mgr_is_held()) {
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    esp_restart();
}

void app_main(void) {
    ESP_LOGI(TAG, "Iniciando SensorHub...");

    // 1. Inicializa almacenamiento NVS e identidad del dispositivo (MAC y topicos)
    ESP_ERROR_CHECK(system_init());

    // LED de estado (modo INICIANDO) y boton de reset de WiFi (no son fatales si no se pueden iniciar)
    led_mgr_init();
    button_mgr_init();

    // 2. Inicializa el WiFi. Sin credenciales guardadas corre el provisioning BLE (no retorna: reinicia al
    // terminar); con credenciales libera la memoria de BLE y sigue.
    ESP_ERROR_CHECK(wifi_mgr_init());
    prov_mgr_run();

    ESP_LOGI(TAG, "Conectando a red WiFi...");
    ESP_ERROR_CHECK(wifi_mgr_connect());
    if (wifi_mgr_wait_connected(pdMS_TO_TICKS(60000)) != ESP_OK) {
        restart_on_failure("Sin IP despues de 1 minuto");
    }

    // 3. Sincroniza la hora por SNTP para el campo "ts" de los payloads.
    // No es fatal: si vence el timeout se sigue sin "ts" (EMQX usa su propia hora) hasta que sincronice.
    ESP_LOGI(TAG, "Sincronizando hora (SNTP)...");
    time_mgr_init(pdMS_TO_TICKS(15000));

    // 4. Inicializa cliente MQTT con client_id unico (MAC del chip)
    ESP_LOGI(TAG, "Iniciando cliente MQTT...");
    ESP_ERROR_CHECK(mqtt_mgr_init(system_get_device_id()));
    if (mqtt_mgr_wait_connected(pdMS_TO_TICKS(10000)) != ESP_OK) {
        restart_on_failure("Sin conexion al broker MQTT despues de 10 s");
    }

    // 5. Despacha e inicia el servicio correspondiente al tipo de dispositivo
    ESP_LOGI(TAG, "Iniciando servicio del dispositivo...");
    ESP_ERROR_CHECK(sensor_service_start());
}
