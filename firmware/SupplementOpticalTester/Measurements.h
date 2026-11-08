#pragma once
#include "LEDController.h"
#include "RGBSensor.h"
#include "LuxSensor.h"

// Centralizes the dark/LED-on measurement sequence and output formatting.
class Measurements {
 public:
  Measurements(LEDController& leds, RGBSensor& rgb, LuxSensor& lux);
  void sweepRGB();
  void sweepLux();
  void sweepCombinedCSV();
  void ambient();
  void csvHeader();

 private:
  LEDController& leds_;
  RGBSensor& rgb_;
  LuxSensor& lux_;
  void sweep(bool needRgb, bool needLux, bool csv);
};
