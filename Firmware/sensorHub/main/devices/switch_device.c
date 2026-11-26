#include "switch_device.h"
#include "system_mgr.h"
#include "mqtt_mgr.h"
#include "time_mgr.h"

#include "cJSON.h"
#include "esp_log.h"
#include <stdbool.h>
#include <string.h>

static const char *TAG = "SWITCH_DEVICE";
// Estado logico actual de la salida (false = "off", true = "on"); inicia apagada
static bool s_current_state = false;

static esp_err_t publish_switch_state(bool is_on) {
    const char *state_str = is_on ? "on" : "off";
    // Crea el objeto de feedback {} y le agrega el campo string "state"
    cJSON *fb = cJSON_CreateObject();
    if (!fb) {
        ESP_LOGE(TAG, "Sin memoria para crear JSON de estado");
        return ESP_ERR_NO_MEM;
    }
    cJSON_AddStringToObject(fb, "state", state_str);
    // Hora de la confirmacion; sin hora valida se omite "ts" y EMQX usa la hora de llegada
    int64_t ts = time_mgr_now_ms();
    if (ts > 0) cJSON_AddNumberToObject(fb, "ts", (double)ts);

    // Serializa el feedback a texto JSON sin espacios (reserva memoria dinamica)
    char *fb_str = cJSON_PrintUnformatted(fb);
    esp_err_t ret = ESP_ERR_NO_MEM;
    if (fb_str) {
        ret = mqtt_mgr_publish_with_flags(system_get_telemetry_topic(), fb_str,
                                          CONFIG_SWITCH_TELEMETRY_QOS, CONFIG_SWITCH_TELEMETRY_RETAIN);
        if (ret == ESP_OK) {
            ESP_LOGI(TAG, "Estado publicado en [%s]: %s", system_get_telemetry_topic(), fb_str);
        } else {
            ESP_LOGW(TAG, "Fallo al publicar estado en [%s]: %s",
                     system_get_telemetry_topic(), esp_err_to_name(ret));
        }
        cJSON_free(fb_str);
    }
    cJSON_Delete(fb);
    return ret;
}

static void on_mqtt_connected(void) {
    // Tras una reconexion (o reinicio de EMQX), republica el estado real de la salida
    ESP_LOGI(TAG, "Reconexion MQTT: republicando estado actual del switch (%s)",
             s_current_state ? "on" : "off");
    publish_switch_state(s_current_state);
}

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

    bool new_state = false;
    if (strcmp(state_item->valuestring, "on") == 0) {
        new_state = true;
    } else if (strcmp(state_item->valuestring, "off") == 0) {
        new_state = false;
    } else {
        ESP_LOGW(TAG, "Valor invalido para 'state': '%s'. Solo se admite \"on\" o \"off\"", state_item->valuestring);
        cJSON_Delete(json);
        return;
    }

    int physical_pin_level = new_state ? CONFIG_SWITCH_ACTIVE_LEVEL : !CONFIG_SWITCH_ACTIVE_LEVEL;
    gpio_set_level(CONFIG_SWITCH_PIN, physical_pin_level);
    s_current_state = new_state;
    ESP_LOGI(TAG, "Switch conmutado a: %s (GPIO %d = nivel %d)",
             s_current_state ? "on" : "off", CONFIG_SWITCH_PIN, physical_pin_level);

    // Feedback al tópico de telemetría en minúsculas estándar (estado + ts)
    publish_switch_state(s_current_state);
    // Libera el JSON parseado del comando
    cJSON_Delete(json);
}

esp_err_t switch_device_start(void) {
    // Limpia cualquier configuracion previa del pin (pulls, funcion alternativa)
    gpio_reset_pin(CONFIG_SWITCH_PIN);
    // Salida push-pull: el ESP32 maneja activamente el rele/carga
    gpio_set_direction(CONFIG_SWITCH_PIN, GPIO_MODE_OUTPUT);
    // Nivel inactivo al arrancar, para que la carga inicie apagada
    gpio_set_level(CONFIG_SWITCH_PIN, !CONFIG_SWITCH_ACTIVE_LEVEL);
    s_current_state = false;

    // Publica el estado inicial ("off") retenido antes de suscribirse a comandos, para que el broker
    // y la base reflejen la salida real tras un arranque o reinicio del nodo
    esp_err_t pub_ret = publish_switch_state(s_current_state);
    if (pub_ret != ESP_OK) {
        ESP_LOGW(TAG, "No se pudo publicar el estado inicial del switch (%s)", esp_err_to_name(pub_ret));
        return pub_ret;
    }

    // Registra callbacks de mensajes entrantes y reconexion MQTT
    mqtt_mgr_set_on_message_callback(on_switch_command);
    mqtt_mgr_set_on_connect_callback(on_mqtt_connected);

    // Suscribe al topico de comandos del actuador
    const char *cmd_topic = system_get_command_topic();
    ESP_LOGI(TAG, "Suscribiendo actuador Switch a topico de comandos: %s", cmd_topic);
    return mqtt_mgr_subscribe(cmd_topic, CONFIG_SWITCH_COMMAND_QOS);
}

