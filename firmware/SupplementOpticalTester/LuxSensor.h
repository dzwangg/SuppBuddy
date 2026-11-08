#pragma once
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_TSL2591.h>

struct LuxReading {
  uint16_t full = 0;      // CH0: visible + infrared. In this rig: light scattered sideways by the sample.
  uint16_t infrared = 0;  // CH1: infrared only. The LEDs emit almost none, so a rise means room light is leaking in.
};

// TSL2591 at 90 degrees to the beam. Gain and integration time stay fixed so runs compare.
class LuxSensor {
 public:
  LuxSensor();
  bool begin(TwoWire& bus);
  bool available() const { return ready_; }
  bool alive();       // still answering on the bus (see RGBSensor::alive)
  LuxReading read();  // one fresh integration (about 120 ms at 100 ms integration)

 private:
  Adafruit_TSL2591 tsl_;
  TwoWire* bus_ = nullptr;
  bool ready_ = false;
};
