#include "wifi_mgr.h"
#include "app_config.h"
#include "led_mgr.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

#if CONFIG_WIFI_MAX_TX_POWER != 0 && (CONFIG_WIFI_MAX_TX_POWER < 8 || CONFIG_WIFI_MAX_TX_POWER > 84)
#error "CONFIG_WIFI_MAX_TX_POWER debe ser 0 (sin limite) o estar entre 8 y 84 (unidades de 0,25 dBm)"
#endif

static const char *TAG = "WIFI_MGR";
static EventGroupHandle_t wifi_event_group;
#define WIFI_CONNECTED_BIT BIT0

static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(wifi_event_group, WIFI_CONNECTED_BIT);
        led_mgr_set_wifi_connected(false);
        wifi_event_sta_disconnected_t *ev = (wifi_event_sta_disconnected_t *)event_data;
        ESP_LOGW(TAG, "Desconectado (reason=%d). Reintentando conexion...", ev->reason);
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(wifi_event_group, WIFI_CONNECTED_BIT);
        led_mgr_set_wifi_connected(true);
        ESP_LOGI(TAG, "Conectado a WiFi y con IP asignada.");
    }
}

esp_err_t wifi_mgr_init(void) {
    wifi_event_group = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
                    ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,
                    IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL));

    wifi_config_t wifi_config = {
        .sta = {
            .ssid = CONFIG_WIFI_SSID,
            .password = CONFIG_WIFI_PASS,
        },
    };

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
#if CONFIG_WIFI_MAX_TX_POWER != 0
    // Limite de potencia para placas que no autentican a potencia maxima (ver app_config.h).
    // Debe llamarse despues de esp_wifi_start().
    ESP_ERROR_CHECK(esp_wifi_set_max_tx_power(CONFIG_WIFI_MAX_TX_POWER));
    ESP_LOGI(TAG, "Potencia de TX limitada a %.2f dBm", CONFIG_WIFI_MAX_TX_POWER * 0.25);
#endif

    return ESP_OK;
}

esp_err_t wifi_mgr_wait_connected(TickType_t timeout_ticks) {
    if (!wifi_event_group) {
        return ESP_ERR_INVALID_STATE;
    }
    EventBits_t bits = xEventGroupWaitBits(
        wifi_event_group,
        WIFI_CONNECTED_BIT,
        pdFALSE,
        pdTRUE,
        timeout_ticks
    );
    return (bits & WIFI_CONNECTED_BIT) ? ESP_OK : ESP_ERR_TIMEOUT;
}

