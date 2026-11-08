#pragma once
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_TCS34725.h>

struct RGBReading {
  float red = 0;
  float green = 0;
  float blue = 0;
  float clear = 0;
};

// TCS34725 in line behind the cuvette: transmitted light in red, green, blue and clear bands.
class RGBSensor {
 public:
  RGBSensor();
  bool begin(TwoWire& bus);
  bool available() const { return ready_; }
  // Averages `count` consecutive integrations. Call it after the light has been steady for at least
  // one integration time, so the first register read is already from the current light.
  RGBReading readAveraged(uint8_t count);

 private:
  Adafruit_TCS34725 tcs_;
  bool ready_ = false;
};
