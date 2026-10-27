cmake_minimum_required(VERSION 3.16)

if(DEFINED DEVICE_TYPE)
    set(ENV{DEVICE_TYPE} "${DEVICE_TYPE}")
endif()

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(sensorHub)

