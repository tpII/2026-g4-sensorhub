# Firmware Modular ESP32 / ESP32-C3: SensorHub Node

### En este documento debe ir toda la informacion asociada a la estructura y diseño del Firmware para los ESP, y cualquier documentacion asociada a los estandares de MQTT o perifericos conectados

Firmware modular desarrollado en **ESP-IDF v5.x** y **FreeRTOS** para la plataforma **SensorHub**. Soporta de manera desacoplada la ingesta de telemetría de sensores (DHT11/22, PIR, etc.) y la recepción de comandos para actuadores (Switch, relés, etc.), comunicándose vía **MQTT** con el broker **EMQX**.

---

## 1. Arquitectura y Estructura del Proyecto

El código está estructurado siguiendo el principio de responsabilidad única (SRP), manteniendo el punto de entrada (`main.c`) agnóstico de los sensores y actuadores físicos:

```text
Firmwares/sensorHub/
├── CMakeLists.txt                 # Definición del proyecto CMake
└── main/
    ├── idf_component.yml          # Dependencias oficiales (esp-idf-lib/dht)
    ├── CMakeLists.txt             # Registro de fuentes y carpetas de include
    ├── app_config.h               # Configuración transversal del sistema (WiFi, MQTT, Dominios)
    ├── main.c                     # Orquestador del sistema
    ├── system_mgr.h / .c          # NVS, identidad de hardware (MAC) y generador de tópicos
    ├── wifi_mgr.h / .c            # Manejador de WiFi STA con auto-reconexión y eventos
    ├── mqtt_mgr.h / .c            # Cliente MQTT universal (MQTT, MQTTS, WS, WSS, Pub/Sub)
    ├── sensor_service.h / .c      # Despachador que arranca la tarea según CONFIG_DEVICE_TYPE
    └── devices/                   # Módulos encapsulados por tipo de dispositivo
        ├── dht_device.h / .c      # Sensor de temperatura y humedad (DHT11/DHT22)
        ├── pir_device.h / .c      # Sensor de presencia y movimiento PIR
        └── switch_device.h / .c      # Actuador Switch / Relé con suscripción a comandos y feedback
```

---

## 2. Catálogo Completo de Variables Configurables

### 2.1. Configuración General del Sistema (`main/app_config.h`)

Este archivo contiene exclusivamente parámetros globales y de red, independientes del sensor o actuador utilizado.

| Parámetro | Valores Posibles | Descripción |
| :--- | :--- | :--- |
| **`CONFIG_WIFI_SSID`** | String (ej: `"MiWiFi"`) | Nombre de la red WiFi 2.4 GHz. |
| **`CONFIG_WIFI_PASS`** | String | Contraseña de la red WiFi. |
| **`CONFIG_SELECTED_PROTOCOL`** | `PROTOCOL_MQTT`<br>`PROTOCOL_MQTTS`<br>`PROTOCOL_WS`<br>`PROTOCOL_WSS` | Protocolo de transporte MQTT:<br>• `PROTOCOL_MQTT`: TCP plano (puerto 1883)<br>• `PROTOCOL_MQTTS`: TLS / SSL (puerto 8883)<br>• `PROTOCOL_WS`: WebSockets (puerto 8083)<br>• `PROTOCOL_WSS`: WebSockets Seguro (puerto 8084) |
| **`CONFIG_BROKER_HOST`** | String (ej: `"broker.emqx.io"`) | Host o IP del broker MQTT. |
| **`CONFIG_WS_PATH`** | String (ej: `"/mqtt"`) | Path para conexiones WebSockets. |
| **`CONFIG_MQTT_TOPIC_PREFIX`** | String (default: `"sensorhub"`) | Espacio de nombres raíz para todos los tópicos. |
| **`CONFIG_DEVICE_TYPE`** | `"dht"`, `"pir"`, `"switch"` | **Tipo de dispositivo a compilar**. Define qué driver y tarea se activan. |
| **`CONFIG_MQTT_USERNAME`** | String | Usuario del broker MQTT (opcional). |
| **`CONFIG_MQTT_PASSWORD`** | String | Contraseña del broker MQTT (opcional). |

NOTA sobre WS: El proyecto utiliza MQTT sobre TCP. El cliente esp-mqtt también soporta MQTT sobre WebSocket, por lo que se dejó la opción seleccionable aquí y el broker tiene habilitado el listener correspondiente. WS debería funcionar sin cambios adicionales, aunque no fue probado. WSS (al igual que MQTTS) requiere configurar en el firmware la CA del broker, ya que actualmente se valida contra el bundle de CAs públicas.

---

### 2.2. Sensor de Clima DHT11 / DHT22 (`main/devices/dht_device.h`)

Encapsula los parámetros físicos y de muestreo del sensor de temperatura y humedad.

| Parámetro | Valores Posibles | Descripción |
| :--- | :--- | :--- |
| **`CONFIG_DHT_PIN`** | `GPIO_NUM_X` | Pin de datos con pull-up interno.<br>• Auto-configurado en `GPIO_NUM_3` para ESP32-C3 SuperMini.<br>• Auto-configurado en `GPIO_NUM_4` para ESP32 clásico / S2 / S3. |
| **`CONFIG_SENSOR_TYPE`** | `SENSOR_TYPE_DHT11`<br>`SENSOR_TYPE_DHT22` | Modelo de sensor conectado (DHT11 vs DHT22 / AM2301 / AM2302). |
| **`CONFIG_SAMPLE_INTERVAL_MS`** | Milisegundos (default: `10000`) | Intervalo de tiempo entre lecturas y publicaciones MQTT. |

---

### 2.3. Sensor de Movimiento PIR (`main/devices/pir_device.h`)

Encapsula los parámetros del detector de presencia por infrarrojo pasivo.

| Parámetro | Valores Posibles | Descripción |
| :--- | :--- | :--- |
| **`CONFIG_PIR_PIN`** | `GPIO_NUM_X` (default: `GPIO_NUM_5`) | Pin de entrada conectado a la salida del sensor PIR. |
| **`CONFIG_PIR_ACTIVE_LEVEL`** | `1` o `0` | Lógica activa de detección:<br>• `1` (Active-High): Detecta movimiento cuando la señal pasa a ALTO (3.3V) — caso común de HC-SR501 y AM312. Configura pull-down interno.<br>• `0` (Active-Low): Detecta movimiento en nivel BAJO (0V). Configura pull-up interno. |

---

### 2.4. Actuador Switch / Relé (`main/devices/switch_device.h`)

Encapsula los parámetros del dispositivo de salida / conmutación.

| Parámetro | Valores Posibles | Descripción |
| :--- | :--- | :--- |
| **`CONFIG_SWITCH_PIN`** | `GPIO_NUM_X` | Pin de salida conectado al switch o bobina del relé.<br>• `GPIO_NUM_8` para el LED integrado en el ESP32-C3 SuperMini.<br>• `GPIO_NUM_2` para el LED integrado en placas ESP32 DevKit. |
| **`CONFIG_SWITCH_ACTIVE_LEVEL`** | `1` o `0` | Nivel lógico de encendido:<br>• `0` (Active-Low): Nivel 0V enciende el actuador (común en ESP32-C3 SuperMini GPIO 8 y módulos de relé optoacoplados).<br>• `1` (Active-High): Nivel 3.3V enciende el actuador (común en ESP32 DevKit GPIO 2). |

---

## 3. Jerarquía de Tópicos MQTT y Payloads Estándar

Los tópicos se construyen automáticamente en tiempo de ejecución con la fórmula canónica:

```text
<CONFIG_MQTT_TOPIC_PREFIX>/<CONFIG_DEVICE_TYPE>/<device_id>/<canal>
```

- **Prefijo:** `sensorhub` (definido en `system_mgr.h`).
- **`device_id`:** Dirección MAC de fábrica del ESP32 en minúsculas (ej. `983dae529858`, `9454c5b096b0`).
- **Regla Global:** Todo el contenido JSON (claves y valores) se define **estrictamente en minúsculas**.

### Resumen de Tópicos y Acciones por Dispositivo

| Dispositivo (`device_type`) | Canal | Tópico Completo | Acción / Disparo | Payload JSON Exacto |
| :--- | :--- | :--- | :--- | :--- |
| **`dht`** | `telemetry` | `sensorhub/dht/<id>/telemetry` | Publicación periódica (cada 10s) | `{"temperature":20.0,"humidity":46.0}` |
| **`pir`** | `telemetry` | `sensorhub/pir/<id>/telemetry` | Detección de movimiento | `{"motion":true}` |
| | `telemetry` | `sensorhub/pir/<id>/telemetry` | Fin de detección / Reposo | `{"motion":false}` |
| **`switch`** | `command` | `sensorhub/switch/<id>/command` | Orden: Encender actuador | `{"state":"on"}` |
| | `command` | `sensorhub/switch/<id>/command` | Orden: Apagar actuador | `{"state":"off"}` |
| | `telemetry` | `sensorhub/switch/<id>/telemetry` | Feedback de estado (Retained) | `{"state":"on"}` o `{"state":"off"}` |
| **`*` (todos)** | `status` | `sensorhub/<type>/<id>/status` | Presencia online / caída LWT (Retained) | `{"online":true}` / `{"online":false}` |

> [IMPORTANTE]
> Para conocer la especificación formal exhaustiva, reglas de filtrado SQL para EMQX/InfluxDB y ejemplos de prueba CLI, consultar el documento en [Stack/MQTT.md](../../Stack/MQTT.md).

## 4. Compilación, Flasheo y Monitoreo (Docker Compose)

Todas las herramientas de compilación y flasheo están contenidas en Docker mediante ESP-IDF oficial v5.2.2 en `Firmwares/utils/`.

### Variables de entorno (`Firmwares/utils/.env`)

```ini
TARGET=esp32c3          # esp32, esp32c3, esp32s3, etc.
PORT=/dev/ttyACM0       # Linux: /dev/ttyACM0 o /dev/ttyUSB0
BAUD=115200             # Baudrate del monitor serie
DEVICE_TYPE=dht         # Tipo a compilar: dht, pir, switch
```

### Compilación nativa con ESP-IDF CLI

```bash
# Vía argumento CMake:
idf.py -DDEVICE_TYPE=switch build

# O vía variable de entorno:
DEVICE_TYPE=pir idf.py clean build
```

---

## 5. Cómo Agregar un Nuevo Dispositivo

Para añadir un nuevo sensor o actuador (por ejemplo, un sensor ultrasónico `"sonar"`):

1. **Crear cabecera e implementación en `main/devices/`:**
   - `devices/sonar_device.h`: Definir pines de trigger/echo y la firma `esp_err_t sonar_device_start(void);`.
   - `devices/sonar_device.c`: Implementar la tarea FreeRTOS, formatear el JSON con `cJSON` y publicar a `system_get_telemetry_topic()`.

2. **Registrar en el despachador (`main/sensor_service.c`):**

   ```c
   #include "sonar_device.h"
   ...
   if (strcmp(type, "sonar") == 0) {
       return sonar_device_start();
   }
   ```

3. **Registrar en `main/CMakeLists.txt`:**
   Agregar `devices/sonar_device.c` a la lista de `SRCS`.

4. **Seleccionar el dispositivo en `main/app_config.h`:**

   ```c
   #define CONFIG_DEVICE_TYPE "sonar"
   ```
