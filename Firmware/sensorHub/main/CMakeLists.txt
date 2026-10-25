if(NOT IDF_VERSION_MAJOR EQUAL 5)
    message(FATAL_ERROR "Este firmware requiere ESP-IDF v5.x (detectado: ${IDF_VERSION_MAJOR}.${IDF_VERSION_MINOR})")
endif()

idf_component_register(
    SRCS "main.c"
         "system_mgr.c"
         "wifi_mgr.c"
         "mqtt_mgr.c"
         "time_mgr.c"
         "sensor_service.c"
         "devices/dht_device.c"
         "devices/pir_device.c"
         "devices/switch_device.c"
    INCLUDE_DIRS "." "devices"
    REQUIRES esp_wifi esp_event nvs_flash mqtt esp_timer json driver mbedtls
)

# Permite definir el tipo de dispositivo desde el build (-DDEVICE_TYPE=... o variable de entorno DEVICE_TYPE)
if(DEFINED ENV{DEVICE_TYPE} AND NOT "$ENV{DEVICE_TYPE}" STREQUAL "")
    target_compile_definitions(${COMPONENT_LIB} PUBLIC CONFIG_DEVICE_TYPE="$ENV{DEVICE_TYPE}")
elseif(DEFINED DEVICE_TYPE AND NOT "${DEVICE_TYPE}" STREQUAL "")
    target_compile_definitions(${COMPONENT_LIB} PUBLIC CONFIG_DEVICE_TYPE="${DEVICE_TYPE}")
endif()
