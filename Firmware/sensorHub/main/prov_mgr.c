#include "prov_mgr.h"
#include "app_config.h"
#include "system_mgr.h"
#include "wifi_mgr.h"
#include "led_mgr.h"

#include "wifi_provisioning/manager.h"
#include "wifi_provisioning/scheme_ble.h"
#include "protocomm_ble.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include <stdio.h>
#include <string.h>

// sdkconfig.defaults activa NimBLE, pero solo se aplica al generar el sdkconfig: uno viejo no lo tiene
#if !defined(CONFIG_BT_NIMBLE_ENABLED)
#error "El provisioning BLE requiere NimBLE: borrar sdkconfig para regenerarlo desde sdkconfig.defaults"
#endif

static const char *TAG = "PROV_MGR";

static EventGroupHandle_t s_prov_event_group;
#define PROV_DONE_BIT BIT0

static bool s_done = false;   // Credenciales validadas: se ignora la desconexion BLE posterior

static void prov_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data) {
    if (event_base == PROTOCOMM_TRANSPORT_BLE_EVENT) {
        if (event_id == PROTOCOMM_TRANSPORT_BLE_CONNECTED) {
            ESP_LOGI(TAG, "App conectada por BLE");
            led_mgr_set_mode(LED_MODE_EXITO);
        } else if (event_id == PROTOCOMM_TRANSPORT_BLE_DISCONNECTED && !s_done) {
            ESP_LOGI(TAG, "App desconectada");
            led_mgr_set_mode(LED_MODE_ESPERANDO_ACCION);
        }
        return;
    }

    switch (event_id) {
        case WIFI_PROV_CRED_RECV: {
            wifi_sta_config_t *sta = (wifi_sta_config_t *)event_data;
            ESP_LOGI(TAG, "Credenciales recibidas para la red [%.*s]. Conectando...", (int)sizeof(sta->ssid), (const char *)sta->ssid);
            led_mgr_set_mode(LED_MODE_INICIANDO);
            break;
        }
        case WIFI_PROV_CRED_FAIL: {
            wifi_prov_sta_fail_reason_t *reason = (wifi_prov_sta_fail_reason_t *)event_data;
            ESP_LOGW(TAG, "No se pudo conectar: %s. Esperando nuevas credenciales...",
                     *reason == WIFI_PROV_STA_AUTH_ERROR ? "contraseña incorrecta" : "red no encontrada");
            // Permite reintentar desde la app sin reiniciar el equipo
            wifi_prov_mgr_reset_sm_state_on_failure();
            led_mgr_set_mode(LED_MODE_ESPERANDO_ACCION);
            break;
        }
        case WIFI_PROV_CRED_SUCCESS:
            ESP_LOGI(TAG, "Provisioning exitoso");
            s_done = true;
            led_mgr_set_mode(LED_MODE_EXITO);
            break;
        case WIFI_PROV_END:
            xEventGroupSetBits(s_prov_event_group, PROV_DONE_BIT);
            break;
        default:
            break;
    }
}

void prov_mgr_run(void) {
    wifi_prov_mgr_config_t config = {
        .scheme = wifi_prov_scheme_ble,
        // Libera la memoria de BT/BLE al terminar (o al desinicializar sin haber provisionado)
        .scheme_event_handler = WIFI_PROV_SCHEME_BLE_EVENT_HANDLER_FREE_BTDM,
    };
    ESP_ERROR_CHECK(wifi_prov_mgr_init(config));

    bool provisioned = false;
    ESP_ERROR_CHECK(wifi_prov_mgr_is_provisioned(&provisioned));
    if (provisioned) {
        wifi_prov_mgr_deinit();
        return;
    }

    s_prov_event_group = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_PROV_EVENT, ESP_EVENT_ANY_ID,
                    &prov_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(PROTOCOMM_TRANSPORT_BLE_EVENT, ESP_EVENT_ANY_ID,
                    &prov_event_handler, NULL, NULL));

    // Nombre BLE: "<prefijo><tipo>_<ultimos 4 hex del device id>" (ej: "PROV_dht_9858")
    const char *id = system_get_device_id();
    char service_name[29];
    snprintf(service_name, sizeof(service_name), "%s%s_%s", CONFIG_PROV_BLE_NAME_PREFIX,
             system_get_device_type(), id + strlen(id) - 4);

    led_mgr_set_mode(LED_MODE_ESPERANDO_ACCION);
    ESP_ERROR_CHECK(wifi_prov_mgr_start_provisioning(WIFI_PROV_SECURITY_1, CONFIG_PROV_POP, service_name, NULL));
    // El manager arranca el WiFi para escanear redes: aplicar el limite de potencia antes de que conecte
    wifi_mgr_apply_tx_power();

    ESP_LOGI(TAG, "Provisioning BLE: abrir la app \"ESP BLE Provisioning\" y elegir [%s] (PoP: %s)", service_name, CONFIG_PROV_POP);
    ESP_LOGI(TAG, "Payload para QR: {\"ver\":\"v1\",\"name\":\"%s\",\"pop\":\"%s\",\"transport\":\"ble\"}", service_name, CONFIG_PROV_POP);

    xEventGroupWaitBits(s_prov_event_group, PROV_DONE_BIT, pdFALSE, pdTRUE, portMAX_DELAY);
    // Deja terminar el patron EXITO; al reiniciar arranca conectandose con las credenciales guardadas
    vTaskDelay(pdMS_TO_TICKS(CONFIG_LED_EXITO_DURATION_MS));
    ESP_LOGI(TAG, "Reiniciando...");
    esp_restart();
}
