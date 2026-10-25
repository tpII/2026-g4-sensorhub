#ifndef SWITCH_DEVICE_H
#define SWITCH_DEVICE_H

#include "esp_err.h"
#include "driver/gpio.h"
#include "sdkconfig.h"

// --- Hardware del Actuador Switch (LED / Relé / Carga Digital) ---
#ifndef CONFIG_SWITCH_PIN
#if defined(CONFIG_IDF_TARGET_ESP32)
    #define CONFIG_SWITCH_PIN           GPIO_NUM_2
#elif defined(CONFIG_IDF_TARGET_ESP32C3)
    #define CONFIG_SWITCH_PIN           GPIO_NUM_8   // LED integrado en placa ESP32-C3 SuperMini
#else
    #define CONFIG_SWITCH_PIN           GPIO_NUM_2
#endif
#endif

// Lógica de encendido: 1 = Activo en Alto (Active-High), 0 = Activo en Bajo (Active-Low)
// Nota: En ESP32-C3 SuperMini el pin en GPIO 8 suele ser Active-Low (0 enciende).
//       En ESP32 DevKit el pin en GPIO 2 suele ser Active-High (1 enciende).
#ifndef CONFIG_SWITCH_ACTIVE_LEVEL
#if defined(CONFIG_IDF_TARGET_ESP32C3)
    #define CONFIG_SWITCH_ACTIVE_LEVEL  0   // 0 = enciende en bajo
#else
    #define CONFIG_SWITCH_ACTIVE_LEVEL  1   // 1 = enciende en alto
#endif
#endif

// Inicia el servicio del actuador Switch (suscripción a comandos y feedback)
esp_err_t switch_device_start(void);

#endif // SWITCH_DEVICE_H

