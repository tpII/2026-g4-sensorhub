#include "button_mgr.h"
#include "app_config.h"
#include "led_mgr.h"
#include "wifi_mgr.h"

#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "BUTTON_MGR";

#define BUTTON_POLL_MS  20

static bool button_pressed(void) {
    return gpio_get_level(CONFIG_RESET_BUTTON_PIN) == CONFIG_RESET_BUTTON_ACTIVE_LEVEL;
}

static void button_task(void *pvParameters) {
    const TickType_t hold_ticks = pdMS_TO_TICKS(CONFIG_RESET_BUTTON_HOLD_MS);

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(BUTTON_POLL_MS));
        if (!button_pressed()) {
            continue;
        }

        ESP_LOGI(TAG, "Boton presionado: mantener %d ms para borrar las credenciales WiFi", CONFIG_RESET_BUTTON_HOLD_MS);
        led_mgr_set_override(LED_MODE_INICIANDO);
        TickType_t start = xTaskGetTickCount();
        bool released = false;
        while (!released && xTaskGetTickCount() - start < hold_ticks) {
            vTaskDelay(pdMS_TO_TICKS(BUTTON_POLL_MS));
            released = !button_pressed();
        }
        if (released) {
            ESP_LOGI(TAG, "Boton soltado antes de tiempo: no se borra nada");
            led_mgr_clear_override();
            continue;
        }

        wifi_mgr_erase_credentials();
        led_mgr_set_override(LED_MODE_EXITO);
        vTaskDelay(pdMS_TO_TICKS(CONFIG_LED_EXITO_DURATION_MS));
        ESP_LOGW(TAG, "Reiniciando en modo provisioning...");
        esp_restart();
    }
}

esp_err_t button_mgr_init(void) {
    if (CONFIG_RESET_BUTTON_PIN == GPIO_NUM_NC) {
        ESP_LOGI(TAG, "Boton de reset deshabilitado (CONFIG_RESET_BUTTON_PIN no definido para este chip)");
        return ESP_OK;
    }

    gpio_config_t io_conf = {
        .pin_bit_mask = 1ULL << CONFIG_RESET_BUTTON_PIN,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = CONFIG_RESET_BUTTON_ACTIVE_LEVEL == 0 ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE,
        .pull_down_en = CONFIG_RESET_BUTTON_ACTIVE_LEVEL == 0 ? GPIO_PULLDOWN_DISABLE : GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t ret = gpio_config(&io_conf);
    if (ret != ESP_OK) {
        return ret;
    }

    if (xTaskCreate(button_task, "button_task", 2560, NULL, 3, NULL) != pdPASS) {
        return ESP_FAIL;
    }
    ESP_LOGI(TAG, "Boton de reset de WiFi en GPIO %d (mantener %d ms)", CONFIG_RESET_BUTTON_PIN, CONFIG_RESET_BUTTON_HOLD_MS);
    return ESP_OK;
}
