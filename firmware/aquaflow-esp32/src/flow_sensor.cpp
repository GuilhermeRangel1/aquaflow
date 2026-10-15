#include "flow_sensor.h"

volatile unsigned long FlowSensor::s_totalPulses = 0;
volatile unsigned long FlowSensor::s_intervalPulses = 0;

void FlowSensor::begin(int pin, float pulsesPerLiter) {
    m_pulsesPerLiter = pulsesPerLiter;
    pinMode(pin, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(pin), FlowSensor::onPulse, FALLING);
}

void IRAM_ATTR FlowSensor::onPulse() {
    s_totalPulses++;
    s_intervalPulses++;
}

float FlowSensor::cumulativeLiters() const {
    noInterrupts();
    unsigned long pulses = s_totalPulses;
    interrupts();
    return pulses / m_pulsesPerLiter;
}

float FlowSensor::instantaneousFlowLitersPerMinute(unsigned long elapsedMs) const {
    noInterrupts();
    unsigned long pulses = s_intervalPulses;
    interrupts();
    if (elapsedMs == 0) {
        return 0.0f;
    }
    float liters = pulses / m_pulsesPerLiter;
    return liters / (static_cast<float>(elapsedMs) / 60000.0f);
}

void FlowSensor::resetInterval() {
    noInterrupts();
    s_intervalPulses = 0;
    interrupts();
}
