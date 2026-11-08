#include "RGBSensor.h"
#include "Config.h"

RGBSensor::RGBSensor() : tcs_(Config::TCS_INTEGRATION, Config::TCS_GAIN) {}

bool RGBSensor::begin(TwoWire& bus) {
  // The breakout's white LED lights the sample from the sensor's side and its glare bounces straight
  // back into the sensor, so keep it off: drive the board's LED pin (wired to TCS_LED_PIN) LOW.
  // This is done first, so the LED is off even if the sensor itself isn't detected.
  ledOff();
  ready_ = tcs_.begin(TCS34725_ADDRESS, &bus);
  // Also covers breakouts whose LED pin is wired to INT instead: enabling the interrupt pulls INT low.
  if (ready_) tcs_.setInterrupt(true);
  return ready_;
}

void RGBSensor::ledOff() {
  pinMode(Config::TCS_LED_PIN, OUTPUT);
  digitalWrite(Config::TCS_LED_PIN, LOW);
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
