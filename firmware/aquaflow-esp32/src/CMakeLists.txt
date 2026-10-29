# Componente "main" do projeto: registra os fontes do firmware e os diretorios de include.
# "." cobre os headers em src/ (flow_sensor.h, telemetry_client.h); "../include" cobre
# config.h e secrets.h. ArduinoJson (header-only) vem via lib_deps do platformio.ini.
idf_component_register(
    SRCS "main.cpp" "flow_sensor.cpp" "telemetry_client.cpp"
    INCLUDE_DIRS "." "../include"
)
