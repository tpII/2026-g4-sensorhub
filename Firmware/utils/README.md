# Utilidad Docker Compose para Flashear y Monitorear ESP32

Este entorno permite compilar, flashear y monitorear cualquier modelo de ESP (`esp32`, `esp32s2`, `esp32s3`, `esp32c3`, `esp32c6`, etc.) utilizando la imagen oficial de ESP-IDF en Docker, tanto en **Linux** como en **Windows**.

---

## Uso Rápido (Linux con Docker Compose)

1. Desde dentro de la carpeta del repo clonada, moverse a:

   ```bash
   cd Firmwares/utils
   cp .env.example .env # Ajustar los valores deseados
   docker compose run --rm flasher
   docker compose run --rm monitor #opcional
   ```

2. Ejecutar el contenedor para compilar y flashear. Reemplazar los valores entre `< >`:

   ```bash
   ls -la /dev/ttyUSB* && ls -la /dev/ttyACM* # Verificar ubicacion puerto

   TARGET=<target> PORT=<puerto> DEVICE_TYPE=<dht|pir|switch> PROJECT_DIR=../sensorHub IDF_IMAGE=espressif/idf:v5.5.6 docker compose run --rm flasher
   ```

3. (Opcional) Abrir el monitor serial en una consola:

   ```bash
   PORT=<puerto> BAUD=115200 docker compose run --rm monitor
   ```

   > Para salir del monitor interactivo, presionar `Ctrl + ]`.

### Parametros disponibles

Los parametros se indican antes del comando `docker compose`. Las opciones disponibles y sus valores por defecto son:

| Parametro | Opciones / formato | Default |
| --- | --- | --- |
| `TARGET` | `esp32`, `esp32s2`, `esp32s3`, `esp32c3`, `esp32c6`, etc. | `esp32` |
| `PORT` | `/dev/ttyUSB0` o `/dev/ttyACM0` | `/dev/ttyUSB0` |
| `BAUD` | Velocidad del monitor serial | `115200` |
| `DEVICE_TYPE` | `dht`, `pir` o `switch` | vacio en Compose; el firmware usa `dht` |
| `PROJECT_DIR` | Ruta al proyecto montado | `../sensorHub` |
| `IDF_IMAGE` | Imagen Docker de ESP-IDF | `espressif/idf:v5.5.6` |

Ejemplo para compilar y flashear:

```bash
<variables> docker compose run --rm flasher
# Ejemplo para esp32 con sensor DHT. Los valores no definidos utilizan los defaults del compose 
TARGET=esp32c3 PORT=/dev/ttyACM0 DEVICE_TYPE=dht docker compose run --rm flasher

TARGET=esp32 PORT=/dev/ttyUSB0 DEVICE_TYPE=pir docker compose run --rm flasher


```

Ejemplo para compilar sin flashear:

```bash
<variables> docker compose run --rm build
```

Ejemplo para flashear sin recompilar:

```bash
<variables> docker compose run --rm flash
```

Ejemplo para abrir el monitor serial:

```bash
<variables> docker compose run --rm monitor
```

### Probar comunicación MQTT (Comandos y Telemetría)

Una vez flasheado el dispositivo y conectado al broker:

```bash
# Escuchar telemetría en tiempo real de cualquier dispositivo:
# (el broker exige usuario: MQTT_MCP_USERNAME / MQTT_MCP_PASSWORD de Stack/.env)
docker run --rm -it eclipse-mosquitto mosquitto_sub -h <host-boker> -u mcp -P "<contraseña>" -t "sensorhub/+/+/telemetry" -v
```

> Para consultar la especificación canónica completa de payloads y tópicos, consultar [Stack/MQTT.md](../../Stack/MQTT.md).

---

## Guía por Sistema Operativo

### Linux

1. Conectar el ESP al puerto USB.
2. Identificar el puerto con:

   ```bash
   ls -la /dev/ttyUSB* && ls -la /dev/ttyACM*
   ```

3. Otorgar permisos al usuario (si no pertenece al grupo `dialout`):

   ```bash
   sudo usermod -aG dialout $USER
   # O temporalmente:
   sudo chmod 666 /dev/ttyUSB0
   ```

4. Ejecutar, indicando todos los parametros del dispositivo para compilar y flashear:

   ```bash
   TARGET=<target> PORT=<puerto> DEVICE_TYPE=<dht|pir|switch> PROJECT_DIR=../sensorHub IDF_IMAGE=espressif/idf:v5.5.6 docker compose run --rm flasher
   ```

5. (Opcional) Abrir el monitor de consola:

   ```bash
   PORT=<puerto> BAUD=115200 docker compose run --rm monitor
   ```

---

### Windows (ESP-IDF nativo) (v5.5.6; ESP-IDF 6.x no es compatible)

   Tambien sirve para Linux utilizando ESP-IDF sin docker

#### Pre-requisitos

1. Instalar ESP-IDF:

   ```powershell
   winget install Espressif.EIM-CLI
   ```

   Reiniciar la consola y luego ejecutar

   ```
   eim install --idf-versions v5.5.6 --target all
   ```

2. Abrir **ESP-IDF PowerShell** o **ESP-IDF Command Prompt**. La configuracion de ESP-IDF es por sesion: no necesariamente queda agregada al PATH global de Windows.
3. Si `idf.py` no es reconocido, localizar y ejecutar el script de exportacion desde PowerShell:

   ```powershell
   # Reemplazar por la ruta de instalacion
   Set-ExecutionPolicy -Scope Process Bypass
   $env:Path="C:\Espressif\tools\python;C:\Espressif\tools\python\v5.5.6\venv\Scripts;$env:Path"
   & "C:\esp\v5.5.6\esp-idf\install.ps1"
   ```

   `install.ps1` crea el entorno Python que necesita ESP-IDF. Ejecutarlo una vez, o nuevamente si aparece un error indicando que falta `python_env`. Cuando termine correctamente, cargar el entorno en la sesion actual:

   ```powershell
   & "C:\esp\v5.5.6\esp-idf\export.ps1"
   ```

   En una consola nueva hay que volver a ejecutar `export.ps1`. No se recomienda agregar manualmente solo `tools` al PATH, porque ESP-IDF tambien necesita su entorno de Python, CMake, Ninja y otras variables.

4. Verificar que el entorno quedo configurado:

   ```powershell
   Get-Command idf.py
   idf.py --version
   ```

5. Conectar el ESP32 por USB.

Para identificar el puerto serie desde PowerShell:

```powershell
Get-CimInstance Win32_SerialPort | Select-Object DeviceID, Description
```

#### Compilar, flashear y monitorear

```powershell
cd Firmwares\sensorHub

# TARGET=esp32 y DEVICE_TYPE=dht son los valores del ejemplo, reemplazar COMX por el puerto correspondiente
idf.py set-target esp32
idf.py -DDEVICE_TYPE=dht clean build
idf.py -p COMX flash monitor -b 115200
```

Los tipos DDEVICE_TYPE son `dht`, `pir` y `switch`. Para salir del monitor serial, presionar `Ctrl+]`.
Otra opcion de set-target podria ser esp32c3

Si solo se quiere compilar:

```powershell
idf.py -DDEVICE_TYPE=dht build
```

Si el firmware ya está compilado y solo se quiere cargar y monitorear:

```powershell
idf.py -p COMX flash monitor -b 115200
```

---

## Errores comunes

> "ERROR: Cannot parse components lock file. Please check that /project/dependencies.lock is a valid lock YAML file." **Solucion:**

- El `dependencies.lock` (o el `sdkconfig`) quedó generado por otra versión de ESP-IDF, por ejemplo una instalación local 5.3 distinta del 5.5.6 de Docker. Ambos son archivos generados y no se versionan: borrarlos (`rm -f Firmware/sensorHub/dependencies.lock Firmware/sensorHub/sdkconfig`) y volver a compilar. El `-f` evita la confirmación cuando los creó el contenedor y pertenecen a `root`.

---

> "'/opt/esp/python_env/idf5.5_py3.12_env/bin/python' is currently active in the environment while the project was configured with '/opt/esp/python_env/idf5.2_py3.10_env/bin/python'. Run 'idf.py fullclean' to start again." **Solucion:**

- La carpeta `build/` fue configurada por otra versión de ESP-IDF (por ejemplo, tras cambiar `IDF_IMAGE`). El `flasher` ya corre `idf.py fullclean`, pero si el `sdkconfig` viejo también quedó de la otra versión puede migrarse mal (por ejemplo, cambiando el target a `esp32`). Borrar `sdkconfig` y `dependencies.lock` como en el error anterior y volver a correr el `flasher`, que regenera todo con `set-target`.

---

> "A fatal error occurred: Serial data stream stopped: Possible serial noise or corruption." **Solucion:**

- Verificar que no haya quedado otra instancia de ESP-IDF que tenga la consola en uso. En el caso de docker verificar con `docker ps`

---

> "A fatal error occurred: Could not open /dev/ttyUSB0, the port is busy or doesn't exist." **Solucion:**

- Verificar el PORT indicado, verificar los dispositivos conectados: `ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null`

---

> "--- Error: device reports readiness to read but returned no data (device disconnected or multiple access on port?)"
> "--- Waiting for the device to reconnect" **Solucion:**

- Hay más de un proceso o contenedor Docker intentando leer del mismo puerto serie de forma concurrente (por ejemplo, un contenedor previo de `flasher` o `monitor` que quedó activo en segundo plano).
- Detener los contenedores huérfanos con:

  ```bash
  docker ps
  docker stop <container_id>
  # O detener todos los servicios de utils:
  docker compose -f Firmwares/utils/docker-compose.yml down
  ```
