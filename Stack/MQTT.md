# Especificación y Catálogo Oficial de Tópicos MQTT (SensorHub)

Este documento es la **especificación y contrato de comunicación MQTT** de la plataforma **SensorHub**, aplicable a los firmwares de borde (ESP32), al broker **EMQX**, y a los motores de ingesta/almacenamiento (**InfluxDB** / Backend).

Estas reglas se configuran tanto en los archivos propios de cada dispositivo ([`devices`](../Firmwares/sensorHub/main/devices/)) como en la configuración del broker ([`broker/emqx.conf.template`](./broker/emqx.conf.template)).

---

## 1. Convención General de Nomenclatura

Todos los tópicos del ecosistema siguen estrictamente la siguiente jerarquía unificada:

```text
sensorhub/<device_type>/<device_id>/<canal>
```

- **`sensorhub`**: Dominio raíz global del proyecto.
- **`<device_type>`**: Tipo o clase funcional del dispositivo (`dht`, `pir`, `switch`). Define de manera unívoca el contrato de datos esperado en el payload.
- **`<device_id>`**: Identificador físico único del microcontrolador. Se obtiene en tiempo de ejecución de la **dirección MAC de fábrica** del chip en minúsculas y sin separadores (ejemplos: `983dae529858`, `9454c5b096b0`), garantizando unicidad global sin requerir aprovisionamiento manual.
- **`<canal>`**: Propósito funcional de la comunicación:
  - **`telemetry`**: Datos continuos de sensado, eventos de detección o acuses de estado publicados por el microcontrolador.
  - **`command`**: Órdenes remotas dirigidas a actuadores suscritos.
  - **`status`**: Disponibilidad y ciclo de vida de conexión del nodo (*Lifecycle & Presence*). Gestionado mediante **LWT (Last Will and Testament)** con bandera `retain = true`.

### Reglas para los Payloads

1. **Formato JSON estricto**: Todos los cuerpos de mensaje deben ser objetos JSON válidos.
2. **Minúsculas obligatorias**: **Todas las claves y valores textuales se definen y procesan exclusivamente en minúsculas** (`"state"`, `"on"`, `"off"`, `"online"`, etc.).
3. **Cero redundancia y payload minimalista**: La identidad del nodo (`device_id`) y su clase funcional (`device_type`) residen exclusivamente en la estructura del tópico MQTT como fuente única de verdad. Los payloads JSON transportan únicamente los datos o mediciones específicos de cada dispositivo, evitando duplicar información y optimizando el ancho de banda.
4. **Cero ambigüedades**: Cada canal y dispositivo tiene una estructura fija y obligatoria. No existen sinónimos ni campos opcionales redundantes.

---

## 2. Catálogo por Dispositivo y Acciones Posibles

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                Catálogo de Dispositivos                                │
├─────────────┬──────────────┬───────────────────┬─────┬─────────────────────────────────┤
│ device_type │ Tipo         │ Canal (accion.ESP)│ QoS │ Acciones                        │
├─────────────┼──────────────┼───────────────────┼─────┼─────────────────────────────────┤
│ dht         │ Sensor       │ telemetry (PUB)   │  1  │ Lectura periódica               │
│ pir         │ Sensor       │ telemetry (PUB)   │  1  │ Evento activo / reposo          │
│ switch      │ Actuador     │ command (SUB)     │  1  │ Conmutar encendido / apag.      │
│             │              │ telemetry (PUB)   │  1  │ Acuse de estado real (Retain)   │
│ * (todos)   │ Cualquiera   │ status (PUB LWT)  │  1  │ Presencia online/offline (Ret)  │
└─────────────┴──────────────┴───────────────────┴─────┴─────────────────────────────────┘
```

- Si la accion en el ESP es de Subscripcion, por tanto el MCP o backend encargado de enviar la señal al dispositivo sera Publicador en ese topico.

---

### Opciones de calidad de servicio en MQTT

| QoS | Nombre        | Garantía                                           | Puede haber duplicados |
| --- | ------------- | -------------------------------------------------- | ---------------------- |
| 0   | At most once  | El mensaje se envía una sola vez, sin confirmación | No                     |
| 1   | At least once | El receptor confirma la recepción, si no hay confirmacion se reenvia luego de un tiempo                 | Sí                     |
| 2   | Exactly once  | Se asegura una única entrega, similar al anterior pero consume mas recursos, obligatorio para acciones tipo "toogle"                       | No                     |

### 2.1. Sensor de Clima: Temperatura y Humedad (`device_type = dht`)

- **Rol en el bus:** Sensor / Productor unidireccional (ESP32 ➔ Broker).
- **Driver asociado:** [`devices/dht_device.c`](../Firmwares/sensorHub/main/devices/dht_device.c) (soporta DHT11 y DHT22).
- **Frecuencia:** Periódica, cada 10 segundos por defecto (`CONFIG_SAMPLE_INTERVAL_MS`).
- **Calidad de servicio:** QoS 1, Retain: `false`.

#### Acción 1: Publicación Periódica de Telemetría

- **Tópico:**

  ```text
  sensorhub/dht/<device_id>/telemetry
  ```

- **Ejemplo real:**

  ```text
  sensorhub/dht/983dae529858/telemetry
  ```

- **Payload JSON:**

  ```json
  {
    "temperature": 20.0,
    "humidity": 46.0
  }
  ```

- **Diccionario de Campos:**

  | Campo | Tipo | Unidad | Descripción |
  | :--- | :--- | :--- | :--- |
  | `temperature` | Float | °C | Temperatura ambiente con 1 decimal. |
  | `humidity` | Float | % | Humedad relativa del aire con 1 decimal. |

- **Canal de comandos:** No aplica (dispositivo solo de salida de datos).

---

### 2.2. Sensor de Presencia y Movimiento (`device_type = pir`)

- **Rol en el bus:** Sensor / Productor de eventos unidireccional (ESP32 ➔ Broker).
- **Driver asociado:** [`devices/pir_device.c`](../Firmwares/sensorHub/main/devices/pir_device.c) (sensores HC-SR501, AM312, etc.).
- **Frecuencia:** Basada en eventos (se evalúa el pin cada 500 ms y **solo publica cuando ocurre una transición de estado**).
- **Calidad de servicio:** QoS 1, Retain: `false`.

#### Acción 1: Notificación de Detección de Movimiento (Evento Activo)

- **Tópico:**

  ```text
  sensorhub/pir/<device_id>/telemetry
  ```

- **Ejemplo real:**

  ```text
  sensorhub/pir/983dae529858/telemetry
  ```

- **Condición:** El nivel en el pin coincide con `CONFIG_PIR_ACTIVE_LEVEL`.

- **Payload JSON:**

  ```json
  {
    "motion": true
  }
  ```

#### Acción 2: Notificación de Zona Despejada (Retorno al Reposo)

- **Tópico:**

  ```text
  sensorhub/pir/<device_id>/telemetry
  ```

- **Condición:** El nivel en el pin deja de coincidir con `CONFIG_PIR_ACTIVE_LEVEL`.

- **Payload JSON:**

  ```json
  {
    "motion": false
  }
  ```

- **Diccionario de Campos:**

  | Campo | Tipo | Valores | Descripción |
  | :--- | :--- | :--- | :--- |
  | `motion` | Boolean | `true` / `false` | `true`: Detección en curso; `false`: Sin movimiento / reposo. |

- **Canal de comandos:** No aplica.

---

### 2.3. Actuador Digital: Switch / Relé (`device_type = switch`)

- **Rol en el bus:** Actuador bidireccional.
  - Escucha órdenes en el canal `command`.
  - Conmuta físicamente el GPIO asignado (`CONFIG_SWITCH_PIN`) respetando el nivel activo (`CONFIG_SWITCH_ACTIVE_LEVEL`).
  - Publica de forma reactiva el estado confirmado en el canal `telemetry`.
- **Driver asociado:** [`devices/switch_device.c`](../Firmwares/sensorHub/main/devices/switch_device.c).
- **Calidad de servicio:** QoS 1 en ambos canales.

#### Acción 1: Encender Actuador (`on`)

1. **Orden de Comando (Backend ➔ ESP32):**
   - **Tópico de Suscripción:**

     ```text
     sensorhub/switch/<device_id>/command
     ```

   - **Ejemplo real:**

     ```text
     sensorhub/switch/9454c5b096b0/command
     ```

   - **Payload JSON Estricto:**

     ```json
     {
       "state": "on"
     }
     ```

2. **Acuse / Telemetría de Confirmación (ESP32 ➔ Broker):**
   - **Tópico de Publicación:**

     ```text
     sensorhub/switch/<device_id>/telemetry
     ```

   - **Ejemplo real:**

     ```text
     sensorhub/switch/9454c5b096b0/telemetry
     ```

   - **Payload JSON:**

     ```json
     {
       "state": "on"
     }
     ```

---

#### Acción 2: Apagar Actuador (`off`)

1. **Orden de Comando (Backend ➔ ESP32):**
   - **Tópico de Suscripción:**

     ```text
     sensorhub/switch/<device_id>/command
     ```

   - **Ejemplo real:**

     ```text
     sensorhub/switch/9454c5b096b0/command
     ```

   - **Payload JSON Estricto:**

     ```json
     {
       "state": "off"
     }
     ```

2. **Acuse / Telemetría de Confirmación (ESP32 ➔ Broker):**
   - **Tópico de Publicación:**

     ```text
     sensorhub/switch/<device_id>/telemetry
     ```

   - **Ejemplo real:**

     ```text
     sensorhub/switch/9454c5b096b0/telemetry
     ```

   - **Payload JSON:**

     ```json
     {
       "state": "off"
     }
     ```

---

#### Contrato Estricto del Parser de Comandos del Actuador

- **Clave admitida:** Únicamente `"state"`. Nombres de clave como `"command"`, `"action"` o `"state_cmd"` son **inválidos**.
- **Valores admitidos:** Únicamente `"on"` o `"off"` en texto minúscula.
- **Respuesta ante payloads no válidos:**
  Si un cliente publica un JSON malformado, sin el campo `"state"`, o con un valor no reconocido (ejemplo: `{"state": "ON"}` o `{"command": "1"}`):
  - El microcontrolador **no conmuta el pin GPIO**.
  - **No emite falso feedback** de telemetría.
  - Emite un mensaje de advertencia en el log serial (`ESP_LOGW`) indicando el payload descartado.

---

### 2.4. Canal Global de Disponibilidad y Estado de Conexión (`canal = status` / LWT)

- **Rol en el bus:** Ciclo de vida y presencia del nodo (ESP32 / Broker ➔ Subscriptores / MCP).
- **Driver asociado:** Integrado en el gestor central [`mqtt_mgr.c`](../Firmwares/sensorHub/main/mqtt_mgr.c) para **todos los tipos de dispositivo** (`dht`, `pir`, `switch`).
- **Calidad de servicio:** QoS 1, Retain: `true`.
- **Tópico:**

  ```text
  sensorhub/<device_type>/<device_id>/status
  ```

- **Ejemplo real:**

  ```text
  sensorhub/switch/983dae529858/status
  ```

#### Funcionamiento de Last Will and Testament (LWT)

1. **Al conectarse al Broker MQTT:**
   - El microcontrolador registra ante el broker su testamento (*Last Will*) en `sensorhub/<device_type>/<device_id>/status` con payload `{"online":false}`, QoS 1 y `retain: true`.
   - Inmediatamente tras establecer la sesión, el microcontrolador publica de forma retenida:

     ```json
     {
       "online": true
     }
     ```

2. **Durante desconexión inesperada (Corte de energía / pérdida de WiFi):**
   - El broker EMQX detecta la pérdida del socket TCP o fallo del *KeepAlive*.
   - El broker despacha automáticamente el testamento retenido:

     ```json
     {
       "online": false
     }
     ```

3. **Consumo por Clientes y Servidores MCP:**
   - Cualquier cliente o servidor MCP que se suscriba a `sensorhub/+/+/status` recibe **inmediatamente** el último estado retenido de cada dispositivo de la red, conociendo qué nodos están operativos sin necesidad de esperar a que fallen los comandos.

- **Diccionario de Campos:**

  | Campo | Tipo | Valores | Descripción |
  | :--- | :--- | :--- | :--- |
  | `online` | Boolean | `true` / `false` | `true`: Nodo conectado y operativo; `false`: Nodo desconectado / caído. |

---

## 3. Comandos de Prueba con Clientes CLI

Algunos ejemplos para probar la comunicación directamente utilizando el contenedor `eclipse-mosquitto` disponible en Docker o clientes locales:

```bash
# 1. Monitorear toda la telemetría del sistema en tiempo real:
docker run --rm -it eclipse-mosquitto mosquitto_sub -h 192.168.0.190 -t "sensorhub/+/+/telemetry" -v

# 2. Monitorear disponibilidad y presencia (LWT) de toda la red:
docker run --rm -it eclipse-mosquitto mosquitto_sub -h 192.168.0.190 -t "sensorhub/+/+/status" -v

# 3. Enviar comando para ENCENDER el actuador Switch de un nodo específico:
docker run --rm eclipse-mosquitto mosquitto_pub -h 192.168.0.190 -t "sensorhub/switch/9454c5b096b0/command" -m '{"state":"on"}'

# 4. Enviar comando para APAGAR el actuador Switch de un nodo específico:
docker run --rm eclipse-mosquitto mosquitto_pub -h 192.168.0.190 -t "sensorhub/switch/9454c5b096b0/command" -m '{"state":"off"}'
```

---

## 4. Patrones de Suscripción Recomendados (Wildcards)

Para servicios de backend, MCP o que corresponda:

| Patrón de Tópico | Propósito |
| :--- | :--- |
| `sensorhub/dht/+/telemetry` | Recibir telemetría climática de **todos los sensores DHT**. |
| `sensorhub/pir/+/telemetry` | Recibir eventos de presencia de **todos los sensores PIR**. |
| `sensorhub/switch/+/telemetry` | Monitorear el acuse y estado retenido de **todos los actuadores Switch**. |
| `sensorhub/+/+/status` | Monitorear la disponibilidad (online/offline) en tiempo real de **todos los nodos mediante LWT**. |
| `sensorhub/+/9454c5b096b0/#` | Monitorear y comandar los canales de **un microcontrolador específico**. |
| `sensorhub/+/+/telemetry` | Canal global de telemetría de **toda la red de dispositivos**. |
| `sensorhub/#` | Escuchar la totalidad del árbol de SensorHub (telemetría, comandos y status). |

---

## 5. Mapeo para Base de Datos Temporal (Reglas SQL de EMQX)

La jerarquía estandarizada permite que el motor de reglas SQL de EMQX extraiga los metadatos de identidad (`device_type` y `device_id`) directamente del path del tópico, manteniendo los payloads limpios y optimizados en el bus MQTT.

Además, para dispositivos de estado discreto (`pir` y `switch`), EMQX aplica una **representación dual en InfluxDB**:

- **Campo semántico (`state` / `motion`):** Preserva el valor original (texto o booleano) para consultas en lenguaje natural, auditoría e integración con agentes de IA vía **MCP** (*Model Context Protocol*).
- **Campo numérico (`value` = `1` / `0`):** Mapeado automáticamente mediante `CASE WHEN` para permitir funciones de agregación temporal matemática (`mean`, `max`, `integral`) y graficar directamente diagramas de pulso/escalón en el **Data Explorer de InfluxDB** o **Grafana** sin errores de tipo.

---

### Regla para Sensores DHT ➔ Measurement `dht_telemetry`

```sql
SELECT
  nth(2, split(topic, '/')) as device_type,
  nth(3, split(topic, '/')) as device_id,
  clientid as client_id,
  payload.temperature as temperature,
  payload.humidity as humidity
FROM "sensorhub/dht/+/telemetry"
```

- **Tags (InfluxDB):** `device_type`, `device_id`
- **Fields (InfluxDB):**
  - `temperature` (float): Temperatura ambiente en °C.
  - `humidity` (float): Humedad relativa en %.

---

### Regla para Sensores PIR ➔ Measurement `pir_telemetry`

```sql
SELECT
  nth(2, split(topic, '/')) as device_type,
  nth(3, split(topic, '/')) as device_id,
  clientid as client_id,
  payload.motion as motion,
  (CASE WHEN payload.motion = true THEN 1 ELSE 0 END) as value
FROM "sensorhub/pir/+/telemetry"
```

- **Tags (InfluxDB):** `device_type`, `device_id`
- **Fields (InfluxDB):**
  - `motion` (boolean): `true` (detección) / `false` (reposo).
  - `value` (integer): `1` (detección) / `0` (reposo) para series de tiempo y gráficos continuos.

---

### Regla para Actuadores Switch ➔ Measurement `switch_telemetry`

```sql
SELECT
  nth(2, split(topic, '/')) as device_type,
  nth(3, split(topic, '/')) as device_id,
  clientid as client_id,
  payload.state as state,
  (CASE WHEN payload.state = 'on' THEN 1 ELSE 0 END) as value
FROM "sensorhub/switch/+/telemetry"
```

- **Tags (InfluxDB):** `device_type`, `device_id`
- **Fields (InfluxDB):**
  - `state` (string): `"on"` (encendido) / `"off"` (apagado).
  - `value` (integer): `1` (encendido) / `0` (apagado) para series de tiempo y gráficos continuos.

---

### Regla para Presencia y Disponibilidad (LWT) ➔ Measurement `device_status`

```sql
SELECT
  nth(2, split(topic, '/')) as device_type,
  nth(3, split(topic, '/')) as device_id,
  clientid as client_id,
  payload.online as online,
  (CASE WHEN payload.online = true THEN 1 ELSE 0 END) as value
FROM "sensorhub/+/+/status"
```

- **Tags (InfluxDB):** `device_type`, `device_id`
- **Fields (InfluxDB):**
  - `online` (boolean): `true` (nodo conectado) / `false` (nodo caído o desconectado).
  - `value` (integer): `1` (online) / `0` (offline) para gráficos de disponibilidad y porcentaje de uptime.
- **Persistencia:** Almacena de forma persistente cada evento de conexión y desconexión abrupta (LWT) en el volumen de InfluxDB, permitiendo a cualquier servidor MCP conocer el estado de disponibilidad incluso tras reinicios en frío del broker EMQX.
