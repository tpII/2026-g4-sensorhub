#include "dht_device.h"
#include "system_mgr.h"
#include "mqtt_mgr.h"
#include "time_mgr.h"

#include <dht.h>
#include "cJSON.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "DHT_DEVICE";

static void dht_task(void *pvParameters) {
    float temp = 0.0f;
    float hum = 0.0f;

#if (CONFIG_SENSOR_TYPE == SENSOR_TYPE_DHT22)
    const dht_sensor_type_t sensor_type = DHT_TYPE_AM2301;
    const char *sensor_name = "DHT22";
#else
    const dht_sensor_type_t sensor_type = DHT_TYPE_DHT11;
    const char *sensor_name = "DHT11";
#endif

    // Solo se activa el pull-up: el bus de un cable del DHT necesita reposar en 1.
    // La direccion del pin (salida open-drain / entrada) la maneja la libreria en cada lectura.
    gpio_set_pull_mode(CONFIG_DHT_PIN, GPIO_PULLUP_ONLY);
    vTaskDelay(pdMS_TO_TICKS(1000));

    ESP_LOGI(TAG, "Iniciado servicio DHT (%s en GPIO %d)", sensor_name, CONFIG_DHT_PIN);

    while (1) {
        esp_err_t err = dht_read_float_data(sensor_type, CONFIG_DHT_PIN, &hum, &temp);
        if (err == ESP_OK) {
            ESP_LOGI(TAG, "Lectura %s -> Temp: %.1f C, Hum: %.1f %%", sensor_name, temp, hum);

            // Hora de la lectura (0 si SNTP aun no sincronizo)
            int64_t ts = time_mgr_now_ms();

            // Construye el payload JSON (métricas del sensor + ts)
            // Crea un objeto JSON vacio {}
            cJSON *root = cJSON_CreateObject();
            // Redondea a un decimal y agrega al objeto JSON Ej 23.46 → 234.6 + 0.5 = 235.1 → 235 → 23.5
            cJSON_AddNumberToObject(root, "temperature", (double)((int)(temp * 10.0f + (temp >= 0 ? 0.5f : -0.5f))) / 10.0);
            // Idem para la humedad (siempre positiva, por eso solo suma 0.5)
            cJSON_AddNumberToObject(root, "humidity", (double)((int)(hum * 10.0f + 0.5f)) / 10.0);
            // Sin hora valida se omite "ts" y EMQX usa la hora de llegada
            if (ts > 0) cJSON_AddNumberToObject(root, "ts", (double)ts);

            // Serializa el objeto a texto JSON sin espacios (reserva memoria dinamica)
            char *json_str = cJSON_PrintUnformatted(root);
            const char *topic = system_get_telemetry_topic();

            if (mqtt_mgr_is_connected()) {
                // Publica el payload JSON en el topic de telemetría
                mqtt_mgr_publish_with_flags(topic, json_str, CONFIG_DHT_TELEMETRY_QOS, CONFIG_DHT_TELEMETRY_RETAIN);
                ESP_LOGI(TAG, "Publicado en [%s]: %s", topic, json_str);
            } else {
                ESP_LOGW(TAG, "MQTT desconectado. Lectura omitida de envio.");
            }

            // Libera el string serializado y luego el objeto JSON
            cJSON_free(json_str);
            cJSON_Delete(root);
        } else {
            ESP_LOGE(TAG, "Fallo al leer %s: %s", sensor_name, esp_err_to_name(err));
        }

        vTaskDelay(pdMS_TO_TICKS(CONFIG_SAMPLE_INTERVAL_MS));
    }
}

esp_err_t dht_device_start(void) {
    BaseType_t ret = xTaskCreate(dht_task, "dht_task", 4096, NULL, 5, NULL);
    // pdPASS (macro de FreeRTOS, = 1) indica que la tarea se creo; si no, falto memoria
    return (ret == pdPASS) ? ESP_OK : ESP_FAIL;
}

