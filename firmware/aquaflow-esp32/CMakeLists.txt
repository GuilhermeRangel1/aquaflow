# Projeto ESP-IDF (Arduino entra como componente via framework = arduino, espidf).
# Boilerplate minimo exigido pelo build system do ESP-IDF; o PlatformIO fornece IDF_PATH.
cmake_minimum_required(VERSION 3.22)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(aquaflow-esp32)
