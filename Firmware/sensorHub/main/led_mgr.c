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

// Patron de cada modo. pulses = 0: se repite mientras dure el modo.
typedef struct {
    uint32_t on_ms;
    uint32_t off_ms;
    uint32_t pulses;
} led_pattern_t;

static const led_pattern_t s_patterns[] = {
    [LED_MODE_NORMAL]           = { CONFIG_LED_NORMAL_ON_MS, 0, 1 },
    [LED_MODE_INICIANDO]        = { CONFIG_LED_INICIANDO_ON_MS, CONFIG_LED_INICIANDO_OFF_MS, 0 },
    [LED_MODE_ESPERANDO_ACCION] = { CONFIG_LED_ESPERANDO_ACCION_ON_MS, CONFIG_LED_ESPERANDO_ACCION_OFF_MS, 0 },
    [LED_MODE_EXITO]            = { CONFIG_LED_EXITO_ON_MS, CONFIG_LED_EXITO_OFF_MS, CONFIG_LED_EXITO_PULSES },
};

// Bits de notificacion de la tarea
#define LED_EVT_MODE_CHANGED            (1 << 0)
#define LED_EVT_ACTIVITY                (1 << 1)

static TaskHandle_t s_led_task = NULL;
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static led_mode_t s_mode = LED_MODE_INICIANDO;
static led_mode_t s_override_mode = LED_MODE_NORMAL;
static bool s_override = false;

static void led_set(bool on) {
    gpio_set_level(CONFIG_STATUS_LED_PIN, on ? CONFIG_STATUS_LED_ACTIVE_LEVEL : !CONFIG_STATUS_LED_ACTIVE_LEVEL);
}

static void led_blink(uint32_t times, uint32_t on_ms, uint32_t off_ms) {
    for (uint32_t i = 0; i < times; i++) {
        led_set(true);
        vTaskDelay(pdMS_TO_TICKS(on_ms));
        led_set(false);
        vTaskDelay(pdMS_TO_TICKS(off_ms));
    }
}

static led_mode_t current_mode(void) {
    taskENTER_CRITICAL(&s_lock);
    led_mode_t mode = s_override ? s_override_mode : s_mode;
    taskEXIT_CRITICAL(&s_lock);
    return mode;
}

static void notify(uint32_t evt) {
    if (s_led_task) {
        xTaskNotify(s_led_task, evt, eSetBits);
    }
}

// Espera ms o hasta que cambie el modo (retorna true en ese caso). Ignora la actividad MQTT.
static bool wait_mode_change(uint32_t ms) {
    TickType_t start = xTaskGetTickCount();
    TickType_t total = pdMS_TO_TICKS(ms);
    TickType_t elapsed;
    while ((elapsed = xTaskGetTickCount() - start) < total) {
        uint32_t events = 0;
        if (xTaskNotifyWait(0, UINT32_MAX, &events, total - elapsed) == pdTRUE && (events & LED_EVT_MODE_CHANGED)) {
            return true;
        }
    }
    return false;
}

static void led_task(void *pvParameters) {
    while (1) {
        led_mode_t mode = current_mode();
        const led_pattern_t *p = &s_patterns[mode];

        if (mode == LED_MODE_NORMAL) {
            led_set(false);
            uint32_t events = 0;
            xTaskNotifyWait(0, UINT32_MAX, &events, portMAX_DELAY);
            if ((events & LED_EVT_ACTIVITY) && current_mode() == LED_MODE_NORMAL) {
                led_blink(p->pulses, p->on_ms, p->off_ms);
            }
        } else if (p->pulses > 0) {
            // Patron finito: se completa entero y despues se vuelve a NORMAL
            led_blink(p->pulses, p->on_ms, p->off_ms);
            taskENTER_CRITICAL(&s_lock);
            if (s_override && s_override_mode == mode) {
                s_override = false;
            } else if (!s_override && s_mode == mode) {
                s_mode = LED_MODE_NORMAL;
            }
            taskEXIT_CRITICAL(&s_lock);
        } else {
            // Parpadeo continuo: cada fase se corta si cambia el modo
            led_set(true);
            if (wait_mode_change(p->on_ms)) {
                continue;
            }
            led_set(false);
            wait_mode_change(p->off_ms);
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

void led_mgr_set_mode(led_mode_t mode) {
    taskENTER_CRITICAL(&s_lock);
    bool changed = (s_mode != mode);
    s_mode = mode;
    taskEXIT_CRITICAL(&s_lock);
    if (changed) {
        notify(LED_EVT_MODE_CHANGED);
    }
}

void led_mgr_set_override(led_mode_t mode) {
    taskENTER_CRITICAL(&s_lock);
    s_override = true;
    s_override_mode = mode;
    taskEXIT_CRITICAL(&s_lock);
    notify(LED_EVT_MODE_CHANGED);
}

void led_mgr_clear_override(void) {
    taskENTER_CRITICAL(&s_lock);
    s_override = false;
    taskEXIT_CRITICAL(&s_lock);
    notify(LED_EVT_MODE_CHANGED);
}

void led_mgr_notify_activity(void) {
    notify(LED_EVT_ACTIVITY);
}
