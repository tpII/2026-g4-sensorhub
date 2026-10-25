#include "mqtt_mgr.h"
#include "app_config.h"
#include "system_mgr.h"
#include "time_mgr.h"
#include "mqtt_client.h"
#include "esp_log.h"
#include "esp_idf_version.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "esp_crt_bundle.h"
#include <string.h>

#if ESP_IDF_VERSION < ESP_IDF_VERSION_VAL(5, 0, 0) || ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(6, 0, 0)
#error "Este firmware requiere ESP-IDF v5.x"
#endif

static const char *TAG = "MQTT_MGR";
static esp_mqtt_client_handle_t client = NULL;
static bool is_connected = false;
static mqtt_msg_callback_t s_msg_callback = NULL;
static char s_subscribed_topic[80] = {0};
static int s_subscribed_qos = 1;

static EventGroupHandle_t s_mqtt_event_group = NULL;
#define MQTT_CONNECTED_BIT BIT0

static void mqtt_event_handler(void *handler_args, esp_event_base_t base,
                               int32_t event_id, void *event_data) {
    esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;

    switch ((esp_mqtt_event_id_t)event_id) {
        case MQTT_EVENT_CONNECTED:
            ESP_LOGI(TAG, "Conectado al broker MQTT (%s)", CONFIG_BROKER_URI);
            is_connected = true;

            // 1. Notificar presencia ONLINE retenida en el canal de status (con "ts" si la hora esta sincronizada)
            char online_msg[48];
            int64_t ts = time_mgr_now_ms();
            if (ts > 0) {
                snprintf(online_msg, sizeof(online_msg), "{\"online\":true,\"ts\":%lld}", ts);
            } else {
                snprintf(online_msg, sizeof(online_msg), "{\"online\":true}");
            }
            esp_mqtt_client_publish(client, system_get_status_topic(), online_msg, 0, 1, 1);
            ESP_LOGI(TAG, "Publicado estado ONLINE retenido en [%s]: %s", system_get_status_topic(), online_msg);

            // 2. Re-suscribir si habia un topico registrado (resiliencia a reconexiones del broker)
            if (s_subscribed_topic[0] != '\0') {
                esp_mqtt_client_subscribe(client, s_subscribed_topic, s_subscribed_qos);
                ESP_LOGI(TAG, "Re-suscrito automaticamente a: %s", s_subscribed_topic);
            }

            if (s_mqtt_event_group) {
                xEventGroupSetBits(s_mqtt_event_group, MQTT_CONNECTED_BIT);
            }
            break;
        case MQTT_EVENT_DISCONNECTED:
            ESP_LOGW(TAG, "Desconectado del broker MQTT");
            is_connected = false;
            if (s_mqtt_event_group) {
                xEventGroupClearBits(s_mqtt_event_group, MQTT_CONNECTED_BIT);
            }
            break;
        case MQTT_EVENT_DATA:
            if (s_msg_callback) {
                s_msg_callback(event->topic, event->topic_len, event->data, event->data_len);
            }
            break;
        case MQTT_EVENT_ERROR:
            ESP_LOGE(TAG, "Error en MQTT: tipo=%d", event->error_handle->error_type);
            break;
        default:
            break;
    }
}

esp_err_t mqtt_mgr_init(const char *client_id) {
    const char *cid = (client_id && strlen(client_id) > 0) ? client_id : "esp32_sensor";

    esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri = CONFIG_BROKER_URI,
        .credentials.client_id = cid,
        .session.last_will = {
            .topic = system_get_status_topic(),
            .msg = "{\"online\":false}",
            .msg_len = 16,
            .qos = 1,
            .retain = 1,
        },
    };
    if (strlen(CONFIG_MQTT_USERNAME) > 0) {
        mqtt_cfg.credentials.username = CONFIG_MQTT_USERNAME;
        mqtt_cfg.credentials.authentication.password = CONFIG_MQTT_PASSWORD;
    }
    #if (CONFIG_SELECTED_PROTOCOL == PROTOCOL_MQTTS || CONFIG_SELECTED_PROTOCOL == PROTOCOL_WSS)
    mqtt_cfg.broker.verification.crt_bundle_attach = esp_crt_bundle_attach;
    #endif

    if (!s_mqtt_event_group) {
        s_mqtt_event_group = xEventGroupCreate();
    } else {
        xEventGroupClearBits(s_mqtt_event_group, MQTT_CONNECTED_BIT);
    }

    client = esp_mqtt_client_init(&mqtt_cfg);
    if (!client) {
        ESP_LOGE(TAG, "Fallo al inicializar cliente MQTT");
        return ESP_FAIL;
    }

    esp_mqtt_client_register_event(client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
    return esp_mqtt_client_start(client);
}

esp_err_t mqtt_mgr_publish_with_flags(const char *topic, const char *data, int qos, int retain) {
    if (!client || !is_connected) {
        return ESP_ERR_INVALID_STATE;
    }
    int msg_id = esp_mqtt_client_publish(client, topic, data, 0, qos, retain);
    return (msg_id >= 0) ? ESP_OK : ESP_FAIL;
}

esp_err_t mqtt_mgr_subscribe(const char *topic, int qos) {
    if (topic) {
        strncpy(s_subscribed_topic, topic, sizeof(s_subscribed_topic) - 1);
        s_subscribed_qos = qos;
    }
    if (!client || !is_connected) {
        return ESP_ERR_INVALID_STATE;
    }
    int msg_id = esp_mqtt_client_subscribe(client, topic, qos);
    return (msg_id >= 0) ? ESP_OK : ESP_FAIL;
}

void mqtt_mgr_set_on_message_callback(mqtt_msg_callback_t cb) {
    s_msg_callback = cb;
}

bool mqtt_mgr_is_connected(void) {
    return is_connected;
}

esp_err_t mqtt_mgr_wait_connected(TickType_t timeout_ticks) {
    if (!s_mqtt_event_group) {
        return ESP_ERR_INVALID_STATE;
    }
    EventBits_t bits = xEventGroupWaitBits(
        s_mqtt_event_group,
        MQTT_CONNECTED_BIT,
        pdFALSE,
        pdTRUE,
        timeout_ticks
    );
    return (bits & MQTT_CONNECTED_BIT) ? ESP_OK : ESP_ERR_TIMEOUT;
}
