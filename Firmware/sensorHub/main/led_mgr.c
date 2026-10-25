#include "led_mgr.h"
#include "app_config.h"
#include "system_mgr.h"
#include "switch_device.h"   // CONFIG_SWITCH_PIN: el LED de estado no debe pisar el pin del actuador

#include "driver/gpio.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>

static const char *TAG = "LED_MGR";

// Tiempos de los patrones de parpadeo (ms)
#define LED_DISCONNECTED_HALF_PERIOD_MS 500   // Sin WiFi: 500 ms encendido / 500 ms apagado (1 parpadeo por segundo)
#define LED_CONNECTED_BLINKS            3     // Al conectar: 3 parpadeos en ~1 s
#define LED_CONNECTED_STEP_MS           166
#define LED_ACTIVITY_ON_MS              50    // Mensaje MQTT: destello corto

// Bits de notificacion de la tarea
#define LED_EVT_WIFI_CHANGED            (1 << 0)
#define LED_EVT_ACTIVITY                (1 << 1)

static TaskHandle_t s_led_task = NULL;
static volatile bool s_wifi_connected = false;

static void led_set(bool on) {
    gpio_set_level(CONFIG_STATUS_LED_PIN, on ? CONFIG_STATUS_LED_ACTIVE_LEVEL : !CONFIG_STATUS_LED_ACTIVE_LEVEL);
}

static void led_blink(int times, int on_ms, int off_ms) {
    for (int i = 0; i < times; i++) {
        led_set(true);
        vTaskDelay(pdMS_TO_TICKS(on_ms));
        led_set(false);
        vTaskDelay(pdMS_TO_TICKS(off_ms));
    }
}

static void led_task(void *pvParameters) {
    bool wifi_up = false;
    bool level = false;

    while (1) {
        // Sin WiFi despierta cada medio periodo para alternar el LED; con WiFi solo ante eventos
        uint32_t events = 0;
        TickType_t wait = wifi_up ? portMAX_DELAY : pdMS_TO_TICKS(LED_DISCONNECTED_HALF_PERIOD_MS);
        xTaskNotifyWait(0, UINT32_MAX, &events, wait);

        if ((events & LED_EVT_WIFI_CHANGED) && s_wifi_connected != wifi_up) {
            wifi_up = s_wifi_connected;
            if (wifi_up) {
                led_blink(LED_CONNECTED_BLINKS, LED_CONNECTED_STEP_MS, LED_CONNECTED_STEP_MS);
            }
        }

        if (!wifi_up) {
            level = !level;
            led_set(level);
        } else if (events & LED_EVT_ACTIVITY) {
            led_blink(1, LED_ACTIVITY_ON_MS, 0);
        }
    }
}

esp_err_t led_mgr_init(void) {
    if (CONFIG_STATUS_LED_PIN == GPIO_NUM_NC) {
        ESP_LOGI(TAG, "LED de estado deshabilitado (CONFIG_STATUS_LED_PIN no definido para este chip)");
        return ESP_OK;
    }
    if (strcmp(system_get_device_type(), "switch") == 0 && CONFIG_STATUS_LED_PIN == CONFIG_SWITCH_PIN) {
        ESP_LOGW(TAG, "LED de estado deshabilitado: GPIO %d lo usa el actuador del switch", CONFIG_STATUS_LED_PIN);
        return ESP_OK;
    }

    gpio_reset_pin(CONFIG_STATUS_LED_PIN);
    gpio_set_direction(CONFIG_STATUS_LED_PIN, GPIO_MODE_OUTPUT);
    led_set(false);

    BaseType_t ret = xTaskCreate(led_task, "led_task", 2048, NULL, 2, &s_led_task);
    if (ret != pdPASS) {
        s_led_task = NULL;
        return ESP_FAIL;
    }
    ESP_LOGI(TAG, "LED de estado en GPIO %d (activo en %d)", CONFIG_STATUS_LED_PIN, CONFIG_STATUS_LED_ACTIVE_LEVEL);
    return ESP_OK;
}

void led_mgr_set_wifi_connected(bool connected) {
    s_wifi_connected = connected;
    if (s_led_task) {
        xTaskNotify(s_led_task, LED_EVT_WIFI_CHANGED, eSetBits);
    }
}

void led_mgr_notify_activity(void) {
    if (s_led_task) {
        xTaskNotify(s_led_task, LED_EVT_ACTIVITY, eSetBits);
    }
}
