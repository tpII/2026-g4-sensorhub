#include "led_mgr.h"
#include "app_config.h"
#include "system_mgr.h"
#include "switch_device.h"   // CONFIG_SWITCH_PIN: el LED de estado no debe pisar el pin del actuador

#include "driver/gpio.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>

// =============================================================================
// Funcionamiento
//
// Una unica tarea (led_task) maneja el GPIO; el resto del firmware solo cambia el modo
// y le avisa con una notificacion. El modo visible sale de dos capas:
//  - Modo del sistema: lo fijan WiFi, provisioning, etc. con led_mgr_set_mode().
//  - Override: lo impone el boton de reset mientras esta presionado. Al quitarlo vuelve
//    a verse el modo del sistema (aunque haya cambiado mientras tanto).
//
// Cada modo tiene un comportamiento:
//  - INICIANDO / ESPERANDO_ACCION: parpadeo continuo hasta que cambie el modo.
//  - EXITO: pulsos sin interrupcion y despues vuelve solo a NORMAL.
//  - NORMAL: apagado; un destello corto por cada aviso de actividad MQTT.
// =============================================================================

static const char *TAG = "LED_MGR";

// Un parpadeo: tiempo encendido y apagado (tiempos en led_mgr.h)
typedef struct {
    uint32_t on_ms;
    uint32_t off_ms;
} led_blink_t;

static const led_blink_t BLINK_INICIANDO        = { CONFIG_LED_INICIANDO_ON_MS, CONFIG_LED_INICIANDO_OFF_MS };
static const led_blink_t BLINK_ESPERANDO_ACCION = { CONFIG_LED_ESPERANDO_ACCION_ON_MS, CONFIG_LED_ESPERANDO_ACCION_OFF_MS };
static const led_blink_t BLINK_EXITO            = { CONFIG_LED_EXITO_ON_MS, CONFIG_LED_EXITO_OFF_MS };
static const led_blink_t BLINK_ACTIVIDAD        = { CONFIG_LED_NORMAL_ON_MS, 0 };

// Avisos que recibe la tarea (bits de notificacion)
#define AVISO_CAMBIO_DE_MODO    (1 << 0)
#define AVISO_ACTIVIDAD_MQTT    (1 << 1)

static TaskHandle_t s_led_task = NULL;
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static led_mode_t s_mode = LED_MODE_INICIANDO;          // Modo del sistema
static led_mode_t s_override_mode = LED_MODE_NORMAL;    // Modo impuesto por el boton
static bool s_override = false;

// --- Estado compartido ---

static led_mode_t current_mode(void) {
    taskENTER_CRITICAL(&s_lock);
    led_mode_t mode = s_override ? s_override_mode : s_mode;
    taskEXIT_CRITICAL(&s_lock);
    return mode;
}

static void avisar(uint32_t aviso) {
    if (s_led_task) {
        xTaskNotify(s_led_task, aviso, eSetBits);
    }
}

// --- Primitivas del LED ---

static void led_set(bool on) {
    gpio_set_level(CONFIG_STATUS_LED_PIN, on ? CONFIG_STATUS_LED_ACTIVE_LEVEL : !CONFIG_STATUS_LED_ACTIVE_LEVEL);
}

// Espera ms, pero vuelve antes (con true) si llega un aviso de cambio de modo.
// Los avisos de actividad MQTT no cortan la espera.
static bool sleep_unless_mode_changes(uint32_t ms) {
    TickType_t start = xTaskGetTickCount();
    TickType_t total = pdMS_TO_TICKS(ms);
    TickType_t elapsed;
    while ((elapsed = xTaskGetTickCount() - start) < total) {
        uint32_t avisos = 0;
        if (xTaskNotifyWait(0, UINT32_MAX, &avisos, total - elapsed) == pdTRUE && (avisos & AVISO_CAMBIO_DE_MODO)) {
            return true;
        }
    }
    return false;
}

// Un parpadeo completo, sin interrupciones
static void blink_once(const led_blink_t *blink) {
    led_set(true);
    vTaskDelay(pdMS_TO_TICKS(blink->on_ms));
    led_set(false);
    vTaskDelay(pdMS_TO_TICKS(blink->off_ms));
}

// --- Comportamiento de cada modo ---

// INICIANDO / ESPERANDO_ACCION: parpadea hasta que cambie el modo (corta en medio del ciclo)
static void show_continuous_blink(const led_blink_t *blink) {
    while (true) {
        led_set(true);
        if (sleep_unless_mode_changes(blink->on_ms)) break;
        led_set(false);
        if (sleep_unless_mode_changes(blink->off_ms)) break;
    }
    led_set(false);
}

// EXITO: pulsos completos y vuelta a NORMAL (salvo que mientras tanto se haya pedido otro modo)
static void show_success(void) {
    for (int i = 0; i < CONFIG_LED_EXITO_PULSES; i++) {
        blink_once(&BLINK_EXITO);
    }

    taskENTER_CRITICAL(&s_lock);
    if (s_override && s_override_mode == LED_MODE_EXITO) {
        s_override = false;
    } else if (!s_override && s_mode == LED_MODE_EXITO) {
        s_mode = LED_MODE_NORMAL;
    }
    taskEXIT_CRITICAL(&s_lock);
}

// NORMAL: apagado hasta el proximo aviso; si es de actividad MQTT, un destello corto
static void show_normal(void) {
    led_set(false);
    uint32_t avisos = 0;
    xTaskNotifyWait(0, UINT32_MAX, &avisos, portMAX_DELAY);
    if ((avisos & AVISO_ACTIVIDAD_MQTT) && current_mode() == LED_MODE_NORMAL) {
        blink_once(&BLINK_ACTIVIDAD);
    }
}

static void led_task(void *pvParameters) {
    while (1) {
        switch (current_mode()) {
            case LED_MODE_INICIANDO:         show_continuous_blink(&BLINK_INICIANDO);        break;
            case LED_MODE_ESPERANDO_ACCION:  show_continuous_blink(&BLINK_ESPERANDO_ACCION); break;
            case LED_MODE_EXITO:             show_success();                                 break;
            case LED_MODE_NORMAL:            show_normal();                                  break;
        }
    }
}

// --- API publica ---

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
        avisar(AVISO_CAMBIO_DE_MODO);
    }
}

void led_mgr_set_override(led_mode_t mode) {
    taskENTER_CRITICAL(&s_lock);
    s_override = true;
    s_override_mode = mode;
    taskEXIT_CRITICAL(&s_lock);
    avisar(AVISO_CAMBIO_DE_MODO);
}

void led_mgr_clear_override(void) {
    taskENTER_CRITICAL(&s_lock);
    s_override = false;
    taskEXIT_CRITICAL(&s_lock);
    avisar(AVISO_CAMBIO_DE_MODO);
}

void led_mgr_notify_activity(void) {
    avisar(AVISO_ACTIVIDAD_MQTT);
}
