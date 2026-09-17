# EMQX Broker & InfluxDB Data Bridge

Este directorio contiene los artefactos de configuración para el broker **EMQX 5** y su pipeline de ingesta automatizada hacia **InfluxDB v2**.

---

## Arquitectura sin valores de entorno hardcodeados

Se implementa patron de **Plantilla + Inyección en Arranque** para facilitar la edicion de valores de entorno solo desde un .env:

1. **Configuración local:** Los secretos y credenciales se definen exclusivamente en `Stack/.env`.
2. **Montaje Docker:** `Stack/docker-compose.yml` inyecta las variables de entorno y monta la carpeta `broker/templates/` junto al script de arranque en el contenedor.
3. **Compilación base:** `broker/docker-entrypoint.sh` sustituye las variables en `templates/emqx.conf.template` generando `/opt/emqx/etc/emqx.conf`.
4. **Descubrimiento dinámico de reglas:** El script recorre `templates/rules/*.conf.template`, compila cada una con sus variables en `/opt/emqx/etc/rules/*.conf` e inyecta automáticamente su correspondiente directiva `include` en `emqx.conf`.
5. **Arranque en frío:** El proceso EMQX 5 inicia consumiendo la configuración de los archivos resultantes, por lo que toda la configuracion del Broker queda almacenada y versionada en el mismo repositorio. Facilitando la replicacion y migracion del proyecto.


- **[`templates/emqx.conf.template`](templates/emqx.conf.template)**: Plantilla base versionada en Git. Define node, dashboard, listeners, autorización y el conector HTTP compartido a InfluxDB.
- **[`templates/rules/`](templates/rules/)**: Directorio modular de reglas por dispositivo (`dht.conf.template`, `pir.conf.template`, `switch.conf.template`, `status.conf.template`).
- **[`docker-entrypoint.sh`](docker-entrypoint.sh)**: Script de arranque dinámico. No requiere modificación al agregar nuevos sensores.
- **`emqx.conf` y `rules/*.conf`**: Archivos resultantes generados en tiempo de arranque dentro del contenedor.

---

## Pipeline de Integración: Tópicos MQTT ➔ InfluxDB

En la edición Open Source (Community Edition) de EMQX, la integración con InfluxDB v2 se realiza de forma nativa mediante **HTTP Actions** enviando **Line Protocol** directamente al endpoint `/api/v2/write`.

La configuración se divide en 3 bloques esenciales:

### 1. Conector Base (`connectors.http.influxdb`)

Establece la conexión de red interna hacia el contenedor de InfluxDB y centraliza la autenticación:

```hocon
connectors {
  http {
    influxdb {
      url = "http://sensorhub_influxdb:8086"
      headers {
        Authorization = "Token ${INFLUXDB_ADMIN_TOKEN}"
        Content-Type = "text/plain; charset=utf-8"
      }
    }
  }
}
```

NOTA: Notar que si bien aca la URL esta "hardcodeada", usa el nombre del contenedor dentro de la red interna de docker, por lo que no deberia porque cambiarse este valor si todo el stack corre en el mismo servidor (y en la misma red de docker)

- **Nota:** Evita repetir la URL y el token en cada acción. Define el pool de conexiones HTTP persistentes para máxima eficiencia.

### 2. Acciones de Formateo Line Protocol (`actions.http.<nombre>`)

Define la ruta de la API de InfluxDB y transforma los campos de la regla al formato *Line Protocol* (`<measurement>,<tags> <fields>`):

```hocon
actions {
  http {
    influx_dht {
      connector = influxdb
      parameters {
        method = post
        path = "/api/v2/write?org=${INFLUXDB_ORG}&bucket=${INFLUXDB_BUCKET}&precision=s"
        body = "dht_telemetry,device_type=${device_type},device_id=${device_id} temperature=${temperature},humidity=${humidity}"
      }
    }
  }
}
```

- **Nota:** InfluxDB v2 requiere Line Protocol plano (`text/plain`). Separamos tags indexables (`device_type`, `device_id`) de los campos de medición. Para actuadores y sensores discretos (`switch` y `pir`), se envían dos campos simultáneos: el semántico (`state="on"` o `motion=true`) y el numérico entero (`value=1i` o `value=0i`), garantizando compatibilidad total tanto con agentes de IA/MCP como con gráficos continuos y agregaciones matemáticas (`mean`) en InfluxDB y Grafana.

### 3. Reglas del Motor SQL (`rule_engine.rules.<nombre>`)

Intercepta los mensajes MQTT entrantes, parsea el JSON, aplica transformaciones lógicas (`CASE WHEN`) y dispara la acción correspondiente:

```hocon
rule_engine {
  rules {
    rule_sensorhub_dht {
      sql = "SELECT nth(2, split(topic, '/')) as device_type, nth(3, split(topic, '/')) as device_id, payload.temperature as temperature, payload.humidity as humidity FROM \"sensorhub/dht/+/telemetry\""
      actions = ["http:influx_dht"]
    }

    rule_sensorhub_switch {
      sql = "SELECT nth(2, split(topic, '/')) as device_type, nth(3, split(topic, '/')) as device_id, payload.state as state, (CASE WHEN payload.state = 'on' THEN 1 ELSE 0 END) as value FROM \"sensorhub/switch/+/telemetry\""
      actions = ["http:influx_switch"]
    }

    rule_sensorhub_status {
      sql = "SELECT nth(2, split(topic, '/')) as device_type, nth(3, split(topic, '/')) as device_id, payload.online as online, (CASE WHEN payload.online = true THEN 1 ELSE 0 END) as value FROM \"sensorhub/+/+/status\""
      actions = ["http:influx_status"]
    }
  }
}
```

- **Nota:** Filtra tópicos de telemetría y presencia, extrae tags del path del tópico y calcula valores derivados numéricos para el almacenamiento analítico en InfluxDB.

---

## Incorporación de Nuevos Dispositivos

### Escenario A: Agregar más dispositivos de tipos ya soportados (`dht`, `pir`, `switch`)
>
> **Estado: 100% Transparente (Cero configuración)**

Gracias al comodín `+` en el tópico MQTT (`sensorhub/dht/+/telemetry`) y la extracción dinámica de `device_id` a partir del path del tópico:

- Se pueden encender cualquier numero de DHT o actuadores Switch adicionales con diferentes MACs.
- Todos se registrarán automáticamente en InfluxDB discriminados por su tag `device_id`.
- **No requiere modificar ningún archivo del stack.**

---

### Escenario B: Agregar un nuevo tipo de dispositivo (Ejemplo: Sensor de Presión `bmp280`)
>
> **Estado: Requiere crear un archivo de plantilla en `templates/rules/`**

Si se diseña un nuevo firmware que publica en `sensorhub/bmp280/<device_id>/telemetry`:

```json
{
  "pressure": 1013.25,
  "temperature": 24.1
}
```

Basta con crear el archivo [`templates/rules/bmp280.conf.template`](templates/rules/) con la acción HTTP y la regla correspondientes:

```hocon
actions {
  http {
    influx_bmp280 {
      connector = influxdb
      enable = true
      parameters {
        method = post
        path = "/api/v2/write?org=${INFLUXDB_ORG}&bucket=${INFLUXDB_BUCKET}&precision=s"
        headers {
          Authorization = "Token ${INFLUXDB_ADMIN_TOKEN}"
          Content-Type = "text/plain; charset=utf-8"
        }
        body = "bmp_telemetry,device_type=${device_type},device_id=${device_id} pressure=${pressure},temperature=${temperature}"
      }
    }
  }
}

rule_engine {
  rules {
    rule_sensorhub_bmp280 {
      sql = "SELECT nth(2, split(topic, '/')) as device_type, nth(3, split(topic, '/')) as device_id, payload.pressure as pressure, payload.temperature as temperature FROM \"sensorhub/bmp280/+/telemetry\""
      enable = true
      description = "Extracción de telemetría barométrica (BMP280) hacia InfluxDB"
      actions = [
        "http:influx_bmp280"
      ]
    }
  }
}
```

#### Aplicar Cambios

Reiniciar el contenedor de EMQX para descubrir, compilar y cargar el nuevo módulo de forma automática:

```bash
cd Stack
docker compose restart emqx
```

*A partir de ese momento, cualquier sensor `bmp280` guardará automáticamente sus métricas bajo la medición `bmp_telemetry` en InfluxDB.*
