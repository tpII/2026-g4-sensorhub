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

// Mientras se mantiene presionado se verifica el nivel cada BUTTON_POLL_MS (detecta que se solto)
#define BUTTON_POLL_MS  20

static TaskHandle_t s_button_task = NULL;
static volatile bool s_held = false;

static bool button_pressed(void) {
    return gpio_get_level(CONFIG_RESET_BUTTON_PIN) == CONFIG_RESET_BUTTON_ACTIVE_LEVEL;
}

// Flanco de presion: despierta la tarea (los rebotes solo acumulan avisos que la tarea descarta)
static void IRAM_ATTR button_isr(void *arg) {
    BaseType_t higher_prio_woken = pdFALSE;
    vTaskNotifyGiveFromISR(s_button_task, &higher_prio_woken);
    portYIELD_FROM_ISR(higher_prio_woken);
}

// Espera hasta cumplir el tiempo de mantenido (true) o hasta que se suelte el boton (false)
static bool wait_hold_completed(void) {
    TickType_t start = xTaskGetTickCount();
    while (xTaskGetTickCount() - start < pdMS_TO_TICKS(CONFIG_RESET_BUTTON_HOLD_MS)) {
        vTaskDelay(pdMS_TO_TICKS(BUTTON_POLL_MS));
        if (!button_pressed()) {
            return false;
        }
    }
    return true;
}

static void button_task(void *pvParameters) {
    while (1) {
        // Bloqueada sin consumir CPU hasta la interrupcion
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        if (!button_pressed()) {
            continue;   // Rebote o aviso viejo
        }

        ESP_LOGI(TAG, "Boton presionado: mantener %d ms para borrar las credenciales WiFi", CONFIG_RESET_BUTTON_HOLD_MS);
        s_held = true;
        led_mgr_set_override(LED_MODE_INICIANDO);

        if (!wait_hold_completed()) {
            ESP_LOGI(TAG, "Boton soltado antes de tiempo: no se borra nada");
            led_mgr_clear_override();
            s_held = false;
            continue;
        }

        // s_held queda en true: los reinicios por falla (main.c) esperan a este
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

    // Prioridad mayor que la de app_main (1): el boton responde aunque el arranque este ocupado
    if (xTaskCreate(button_task, "button_task", 2560, NULL, 3, &s_button_task) != pdPASS) {
        return ESP_FAIL;
    }

    gpio_config_t io_conf = {
        .pin_bit_mask = 1ULL << CONFIG_RESET_BUTTON_PIN,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = CONFIG_RESET_BUTTON_ACTIVE_LEVEL == 0 ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE,
        .pull_down_en = CONFIG_RESET_BUTTON_ACTIVE_LEVEL == 0 ? GPIO_PULLDOWN_DISABLE : GPIO_PULLDOWN_ENABLE,
        .intr_type = CONFIG_RESET_BUTTON_ACTIVE_LEVEL == 0 ? GPIO_INTR_NEGEDGE : GPIO_INTR_POSEDGE,
    };
    esp_err_t ret = gpio_config(&io_conf);
    if (ret == ESP_OK) {
        // El servicio de ISR de GPIO lo instala system_init()
        ret = gpio_isr_handler_add(CONFIG_RESET_BUTTON_PIN, button_isr, NULL);
    }
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "No se pudo configurar el boton de reset: %s", esp_err_to_name(ret));
        return ret;
    }

    ESP_LOGI(TAG, "Boton de reset de WiFi en GPIO %d (mantener %d ms)", CONFIG_RESET_BUTTON_PIN, CONFIG_RESET_BUTTON_HOLD_MS);
    return ESP_OK;
}

bool button_mgr_is_held(void) {
    return s_held;
}
