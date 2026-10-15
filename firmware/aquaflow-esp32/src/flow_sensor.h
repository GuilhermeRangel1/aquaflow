#pragma once

#include <Arduino.h>

// Conta pulsos de um sensor de vazao por interrupcao e deriva volume e vazao.
// O contador de pulsos e volatile porque e incrementado dentro de uma ISR.
class FlowSensor {
public:
    void begin(int pin, float pulsesPerLiter);

    // Le o contador acumulado desde o boot, em litros.
    float cumulativeLiters() const;

    // Calcula a vazao media (L/min) desde a ultima chamada a resetInterval().
    float instantaneousFlowLitersPerMinute(unsigned long elapsedMs) const;

    // Zera o contador de pulsos do intervalo atual, mantendo o acumulado total.
    void resetInterval();

private:
    static void IRAM_ATTR onPulse();

    static volatile unsigned long s_totalPulses;
    static volatile unsigned long s_intervalPulses;
    float m_pulsesPerLiter = 1.0f;
};
