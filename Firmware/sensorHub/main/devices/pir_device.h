#ifndef PIR_DEVICE_H
#define PIR_DEVICE_H

#include "esp_err.h"
#include "driver/gpio.h"

// --- Hardware del Sensor PIR ---
#define CONFIG_PIR_PIN                  GPIO_NUM_5

// Lógica de detección: 1 = Detecta movimiento en Alto (Active-High), 0 = Detecta en Bajo (Active-Low)
// La mayoría de los sensores PIR comerciales (HC-SR501, AM312) entregan nivel ALTO (3.3V) al detectar movimiento.
#define CONFIG_PIR_ACTIVE_LEVEL         1

// --- MQTT (ver wiki 03, catálogo por dispositivo) ---
// Sin retain: eventos esporádicos y time-sensitive
#define CONFIG_PIR_TELEMETRY_QOS        1
#define CONFIG_PIR_TELEMETRY_RETAIN     0

// Inicia el servicio del sensor de presencia PIR
esp_err_t pir_device_start(void);

#endif // PIR_DEVICE_H
