#include "pir_device.h"
#include "system_mgr.h"
#include "mqtt_mgr.h"
#include "time_mgr.h"

#include "cJSON.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"

static const char *TAG = "PIR_DEVICE";

// Antirrebote: la senal debe quedar estable este tiempo sin flancos para aceptarse.
// Los PIR mantienen su salida por segundos, asi que un pulso mas corto es ruido (alimentacion, cableado).
#define PIR_DEBOUNCE_MS 200

// ISR: solo avisa a la tarea que hubo un flanco (sin logica pesada en contexto de interrupcion)
static void IRAM_ATTR pir_isr_handler(void *arg) {
    TaskHandle_t task = (TaskHandle_t)arg;
    BaseType_t higher_prio_woken = pdFALSE;
    vTaskNotifyGiveFromISR(task, &higher_prio_woken);
    portYIELD_FROM_ISR(higher_prio_woken);
}

static void pir_task(void *pvParameters) {
    ESP_LOGI(TAG, "Iniciado servicio de sensor PIR en GPIO %d", CONFIG_PIR_PIN);

    // Entrada con pull opuesto al nivel activo (activo en 1 -> pull-down, activo en 0 -> pull-up),
    // para que el pin no flote cuando el sensor esta en reposo.
    // intr_type ANYEDGE: interrumpe en flanco de subida y de bajada.
    gpio_config_t io_conf = {
        .intr_type = GPIO_INTR_ANYEDGE,
        .pin_bit_mask = (1ULL << CONFIG_PIR_PIN),
        .mode = GPIO_MODE_INPUT,
        .pull_down_en = (CONFIG_PIR_ACTIVE_LEVEL == 1) ? GPIO_PULLDOWN_ENABLE : GPIO_PULLDOWN_DISABLE,
        .pull_up_en = (CONFIG_PIR_ACTIVE_LEVEL == 0) ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE,
    };
    gpio_config(&io_conf);

    // El servicio de ISR de GPIO se instala una vez en system_init()
    ESP_ERROR_CHECK(gpio_isr_handler_add(CONFIG_PIR_PIN, pir_isr_handler, xTaskGetCurrentTaskHandle()));

    int last_state = -1;

    while (1) {
        // Bloquea sin consumir CPU hasta un flanco (en el primer ciclo no espera, para publicar el estado inicial)
        if (last_state != -1) {
            ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
            // Antirrebote: espera hasta que pasen PIR_DEBOUNCE_MS sin ningun flanco nuevo
            while (ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(PIR_DEBOUNCE_MS)) > 0) {
            }
        }

        int current_state = gpio_get_level(CONFIG_PIR_PIN);
        if (current_state != last_state) {
            last_state = current_state;

            bool motion = (current_state == CONFIG_PIR_ACTIVE_LEVEL);

            // Crea un objeto JSON vacio {}
            cJSON *root = cJSON_CreateObject();
            // Agrega el campo booleano "motion": true/false
            cJSON_AddBoolToObject(root, "motion", motion);
            // Hora del evento; sin hora valida se omite "ts" y EMQX usa la hora de llegada
            int64_t ts = time_mgr_now_ms();
            if (ts > 0) cJSON_AddNumberToObject(root, "ts", (double)ts);

            // Serializa el objeto a texto JSON sin espacios (reserva memoria dinamica)
            char *json_str = cJSON_PrintUnformatted(root);
            const char *topic = system_get_telemetry_topic();

            if (mqtt_mgr_is_connected()) {
                mqtt_mgr_publish_with_flags(topic, json_str, CONFIG_PIR_TELEMETRY_QOS, CONFIG_PIR_TELEMETRY_RETAIN);
                ESP_LOGI(TAG, "Evento PIR publicado en [%s]: %s", topic, json_str);
            }

            // Libera el string serializado y luego el objeto JSON
            cJSON_free(json_str);
            cJSON_Delete(root);
        }
    }
}

esp_err_t pir_device_start(void) {
    BaseType_t ret = xTaskCreate(pir_task, "pir_task", 4096, NULL, 5, NULL);
    // pdPASS (macro de FreeRTOS, = 1) indica que la tarea se creo; si no, falto memoria
    return (ret == pdPASS) ? ESP_OK : ESP_FAIL;
}

