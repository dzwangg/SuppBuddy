#pragma once
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_TCS34725.h>

struct RGBReading {
  int32_t red = 0;
  int32_t green = 0;
  int32_t blue = 0;
  int32_t clear = 0;
};

class RGBSensor {
 public:
  RGBSensor();
  bool begin(TwoWire& bus);
  bool available() const { return ready_; }
  RGBReading read();
  static RGBReading difference(const RGBReading& on,
                               const RGBReading& off);
  // A rough label for demonstrations; NOT a calibrated color measurement.
  static const char* approximateColor(const RGBReading& corrected);

 private:
  Adafruit_TCS34725 tcs_;
  bool ready_ = false;
};
