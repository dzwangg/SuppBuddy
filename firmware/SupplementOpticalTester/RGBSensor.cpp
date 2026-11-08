#include "RGBSensor.h"
#include "Config.h"

RGBSensor::RGBSensor() : tcs_(Config::TCS_INTEGRATION, Config::TCS_GAIN) {}

bool RGBSensor::begin(TwoWire& bus) {
  bus_ = &bus;
  ready_ = tcs_.begin(TCS34725_ADDRESS, &bus);
  // On breakouts whose white illumination LED is wired to INT, this turns that LED off.
  // Boards without that link need the LED pin tied to GND (see README).
  if (ready_) tcs_.setInterrupt(true);
  return ready_;
}

bool RGBSensor::alive() {
  if (!ready_ || !bus_) return false;
  bus_->beginTransmission(TCS34725_ADDRESS);
  return bus_->endTransmission() == 0;  // ACKed its address
}

RGBReading RGBSensor::readAveraged(uint8_t count) {
  RGBReading out;
  if (!ready_ || count == 0) return out;
  uint32_t r = 0, g = 0, b = 0, c = 0;
  for (uint8_t i = 0; i < count; ++i) {
    uint16_t rr, gg, bb, cc;
    tcs_.getRawData(&rr, &gg, &bb, &cc);  // reads the last finished integration, then waits one more
    r += rr; g += gg; b += bb; c += cc;
  }
  out.red = (float)r / count;
  out.green = (float)g / count;
  out.blue = (float)b / count;
  out.clear = (float)c / count;
  return out;
}
