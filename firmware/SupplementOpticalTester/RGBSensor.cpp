#include "RGBSensor.h"
#include <math.h>

RGBSensor::RGBSensor()
  : tcs_(TCS34725_INTEGRATIONTIME_50MS, TCS34725_GAIN_4X) {}

bool RGBSensor::begin(TwoWire& bus) {
  ready_ = tcs_.begin(TCS34725_ADDRESS, &bus);
  // If your breakout includes an always-on white illumination LED,
  // physically shield/disable it for transmission measurements.
  return ready_;
}

RGBReading RGBSensor::read() {
  RGBReading out;
  if (!ready_) return out;
  uint16_t r = 0, g = 0, b = 0, c = 0;
  tcs_.getRawData(&r, &g, &b, &c);
  out.red = r; out.green = g; out.blue = b; out.clear = c;
  return out;
}

RGBReading RGBSensor::difference(const RGBReading& on,
                                 const RGBReading& off) {
  RGBReading out;
  out.red = on.red - off.red;
  out.green = on.green - off.green;
  out.blue = on.blue - off.blue;
  out.clear = on.clear - off.clear;
  return out;
}

const char* RGBSensor::approximateColor(const RGBReading& d) {
  const float r = fmaxf(0.0f, (float)d.red);
  const float g = fmaxf(0.0f, (float)d.green);
  const float b = fmaxf(0.0f, (float)d.blue);
  const float maximum = fmaxf(r, fmaxf(g, b));
  const float minimum = fminf(r, fminf(g, b));
  if (d.clear < 40 || maximum < 30) return "NO LIGHT / LOW SIGNAL";
  const float delta = maximum - minimum;
  if (delta / maximum < 0.18f) return "WHITE / NEUTRAL";
  float hue;
  if (maximum == r) hue = 60.0f * (g - b) / delta;
  else if (maximum == g) hue = 60.0f * ((b - r) / delta + 2.0f);
  else hue = 60.0f * ((r - g) / delta + 4.0f);
  if (hue < 0) hue += 360.0f;
  if (hue < 15 || hue >= 345) return "RED";
  if (hue < 45) return "ORANGE";
  if (hue < 75) return "YELLOW";
  if (hue < 165) return "GREEN";
  if (hue < 205) return "LIGHT BLUE";
  if (hue < 260) return "BLUE";
  if (hue < 290) return "PURPLE";
  return "PINK / MAGENTA";
}
