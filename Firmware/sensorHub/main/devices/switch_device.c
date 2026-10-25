#include "switch_device.h"
#include "system_mgr.h"
#include "mqtt_mgr.h"

#include "cJSON.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "SWITCH_DEVICE";

static void on_switch_command(const char *topic, int topic_len, const char *data, int data_len) {
    char topic_buf[96] = {0};
    char data_buf[256] = {0};

    if (topic_len < (int)sizeof(topic_buf)) strncpy(topic_buf, topic, topic_len);
    if (data_len < (int)sizeof(data_buf)) strncpy(data_buf, data, data_len);

    const char *expected_cmd_topic = system_get_command_topic();
    if (strcmp(topic_buf, expected_cmd_topic) != 0) {
        return;
    }

    ESP_LOGI(TAG, "Comando recibido en [%s]: %s", topic_buf, data_buf);

    // Parsea el texto recibido a un arbol JSON (NULL si es invalido; hay que liberarlo con cJSON_Delete)
    cJSON *json = cJSON_Parse(data_buf);
    if (!json) {
        ESP_LOGE(TAG, "JSON de comando invalido");
        return;
    }

    // Estándar estricto: único campo permitido "state", valores en minúscula "on" u "off"
    // Busca el campo "state" en el objeto (NULL si no existe; no hay que liberarlo por separado)
    cJSON *state_item = cJSON_GetObjectItem(json, "state");
    if (!state_item || !cJSON_IsString(state_item) || !state_item->valuestring) {
        ESP_LOGW(TAG, "Payload invalido: se requiere campo 'state' como string (\"on\" o \"off\")");
        cJSON_Delete(json);
        return;
    }

    int new_level = -1;
    if (strcmp(state_item->valuestring, "on") == 0) {
        new_level = 1;
    } else if (strcmp(state_item->valuestring, "off") == 0) {
        new_level = 0;
    } else {
        ESP_LOGW(TAG, "Valor invalido para 'state': '%s'. Solo se admite \"on\" o \"off\"", state_item->valuestring);
        cJSON_Delete(json);
        return;
    }

    int physical_pin_level = (new_level == 1) ? CONFIG_SWITCH_ACTIVE_LEVEL : !CONFIG_SWITCH_ACTIVE_LEVEL;
    gpio_set_level(CONFIG_SWITCH_PIN, physical_pin_level);
    ESP_LOGI(TAG, "Switch conmutado a: %s (GPIO %d = nivel %d)",
             new_level ? "on" : "off", CONFIG_SWITCH_PIN, physical_pin_level);

    // Feedback al tópico de telemetría en minúsculas estándar (solo el estado)
    const char *state_str = new_level ? "on" : "off";
    // Crea el objeto de feedback {} y le agrega el campo string "state"
    cJSON *fb = cJSON_CreateObject();
    cJSON_AddStringToObject(fb, "state", state_str);

    // Serializa el feedback a texto JSON sin espacios (reserva memoria dinamica)
    char *fb_str = cJSON_PrintUnformatted(fb);
    if (fb_str) {
        mqtt_mgr_publish_with_flags(system_get_telemetry_topic(), fb_str, 1, 1);
        ESP_LOGI(TAG, "Feedback enviado (retained) a [%s]: %s", system_get_telemetry_topic(), fb_str);
        cJSON_free(fb_str);
    }
    // Libera el objeto de feedback y el JSON parseado del comando
    cJSON_Delete(fb);
    cJSON_Delete(json);
}

esp_err_t switch_device_start(void) {
    // Limpia cualquier configuracion previa del pin (pulls, funcion alternativa)
    gpio_reset_pin(CONFIG_SWITCH_PIN);
    // Salida push-pull: el ESP32 maneja activamente el rele/carga
    gpio_set_direction(CONFIG_SWITCH_PIN, GPIO_MODE_OUTPUT);
    // Nivel inactivo al arrancar, para que la carga inicie apagada
    gpio_set_level(CONFIG_SWITCH_PIN, !CONFIG_SWITCH_ACTIVE_LEVEL);

    // Registra callback de mensajes entrantes
    mqtt_mgr_set_on_message_callback(on_switch_command);

    // Suscribe al topico de comandos del actuador
    const char *cmd_topic = system_get_command_topic();
    ESP_LOGI(TAG, "Suscribiendo actuador Switch a topico de comandos: %s", cmd_topic);
    return mqtt_mgr_subscribe(cmd_topic, 1);
}

