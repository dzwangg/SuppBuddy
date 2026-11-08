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
  bool begin(TwoWire& bus);  // also turns the breakout's white LED off
  bool available() const { return ready_; }
  static void ledOff();       // drives the breakout's LED pin (Config::TCS_LED_PIN) LOW
  // Still answering on the bus. A sensor that drops off mid-run (loose wire, power dip) doesn't fail a
  // read: the driver returns stale register contents, which look like a real, very dark sample.
  bool alive();
  // Averages `count` consecutive integrations. Call it after the light has been steady for at least
  // one integration time, so the first register read is already from the current light.
  RGBReading readAveraged(uint8_t count);

 private:
  Adafruit_TCS34725 tcs_;
  TwoWire* bus_ = nullptr;
  bool ready_ = false;
};
