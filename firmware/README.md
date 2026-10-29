# Firmware ESP32

Esta pasta reúne o contrato e o protótipo do firmware ESP32. O protótipo em
[`aquaflow-esp32/`](aquaflow-esp32/) já compila e publica telemetria por **MQTT**, mas
**ainda não foi validado em hardware real**: o modelo de ESP32, o sensor de vazão, os pinos
e a calibração ainda dependem de verificação física. A telemetria que aparece na conta demo
e os dados do treinamento de ML são simulados.

O [guia de integração](docs/integracao-esp32.md) mostra como provisionar um medidor e verificar o contrato pela API HTTP sem firmware. O [contrato MQTT](../docs/contrato-mqtt.md) descreve a publicação aceita pelo broker local e também demonstra o envio com um publicador de teste. Essas verificações não equivalem a validar uma placa ou sensor físico. Antes de conectar um dispositivo físico ao broker por outra rede, será preciso oferecer acesso de rede com TLS e credenciais individuais, como indicado nesse contrato.

## Responsabilidades previstas no FreeRTOS

- Contar os pulsos do sensor sem perder eventos e converter para volume/vazão com calibração medida.
- Registrar cada amostra com relógio sincronizado, identificador de evento estável e número de série provisionado.
- Manter uma fila local limitada para reenvio quando a rede cair; repetir o mesmo evento sem alterar seu conteúdo.
- Publicar telemetria pelo transporte escolhido, sem incluir chaves no corpo da leitura ou nos logs.

O protótipo publica por MQTT (transporte do projeto); o armazenamento da fila e os limites de amostragem ainda dependem do hardware. O backend não deve depender da implementação do firmware: a interface entre as partes é o contrato de telemetria.
