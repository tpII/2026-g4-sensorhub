#ifndef SYSTEM_MGR_H
#define SYSTEM_MGR_H

#include "esp_err.h"

// Inicializa NVS Flash e identidad del dispositivo (MAC y topicos)
esp_err_t system_init(void);

// Retorna el identificador unico del dispositivo (MAC WiFi en hexadecimal, minusculas, sin separadores)
const char* system_get_device_id(void);

// Retorna el tipo de dispositivo configurado ("dht", "pir", "switch", etc.)
const char* system_get_device_type(void);

// Retorna el topico de publicacion de telemetria
// Formato: <prefix>/<type>/<id>/telemetry  (ej: "sensorhub/dht/983dae529858/telemetry")
const char* system_get_telemetry_topic(void);

// Retorna el topico de recepcion de comandos
// Formato: <prefix>/<type>/<id>/command    (ej: "sensorhub/switch/983dae529858/command")
const char* system_get_command_topic(void);

// Retorna el topico de presencia y disponibilidad (Last Will and Testament)
// Formato: <prefix>/<type>/<id>/status     (ej: "sensorhub/switch/983dae529858/status")
const char* system_get_status_topic(void);

#endif // SYSTEM_MGR_H

