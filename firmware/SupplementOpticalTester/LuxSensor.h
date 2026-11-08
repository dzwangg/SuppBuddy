#pragma once
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_TSL2591.h>

struct LuxReading {
  uint16_t full = 0;       // TSL2591 CH0: broadband (visible + IR)
  uint16_t infrared = 0;   // TSL2591 CH1: IR-sensitive
  int32_t visible = 0;     // Derived: full - infrared
  float lux = NAN;         // Derived: lux estimate, NAN when invalid
  bool valid = false;
};

class LuxSensor {
 public:
  LuxSensor();
  bool begin(TwoWire& bus);
  bool available() const { return ready_; }
  LuxReading read();

 private:
  Adafruit_TSL2591 tsl_;
  bool ready_ = false;
};
