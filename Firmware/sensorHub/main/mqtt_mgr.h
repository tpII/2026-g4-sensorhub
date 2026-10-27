#ifndef MQTT_MGR_H
#define MQTT_MGR_H

#include <stdbool.h>
#include "esp_err.h"
#include "freertos/FreeRTOS.h"

// Tipo de callback para recepcion de mensajes MQTT (actuadores/comandos)
typedef void (*mqtt_msg_callback_t)(const char *topic, int topic_len, const char *data, int data_len);

// Inicializa el cliente MQTT con el protocolo seleccionado en app_config.h y el client_id indicado
esp_err_t mqtt_mgr_init(const char *client_id);

// Publica un mensaje con QoS y flag Retain especificos (cada device define los suyos en su header)
esp_err_t mqtt_mgr_publish_with_flags(const char *topic, const char *data, int qos, int retain);

// Suscribe a un topico MQTT
esp_err_t mqtt_mgr_subscribe(const char *topic, int qos);

// Registra callback para mensajes entrantes
void mqtt_mgr_set_on_message_callback(mqtt_msg_callback_t cb);

// Retorna true si el cliente esta conectado al broker
bool mqtt_mgr_is_connected(void);

// Bloquea hasta que el cliente MQTT se conecte al broker o expire el timeout
esp_err_t mqtt_mgr_wait_connected(TickType_t timeout_ticks);

#endif // MQTT_MGR_H
