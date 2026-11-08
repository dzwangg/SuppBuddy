#pragma once
#include <Arduino.h>
#include <functional>
#include "LEDController.h"
#include "RGBSensor.h"
#include "LuxSensor.h"

struct Reading {
  RGBReading rgb;
  LuxReading lux;
};

// Runs the protocol v3 sequences and formats their lines (repo README, "BLE contract").
//   blank: I, D, then B for each LED, then E
//   run:   I, then every cycle K (dark) + S for each LED, for Config::RUN_SECONDS, then E
// A missing sensor answers "X,<reason>" followed by E, so the app can show the reason.
class Measurements {
 public:
  using Send = std::function<void(const String&)>;
  using KeepGoing = std::function<bool()>;

  Measurements(LEDController& leds, RGBSensor& rgb, LuxSensor& lux);
  void info(const Send& send);
  void blank(const Send& send);
  void run(const Send& send, const KeepGoing& keepGoing);
  Reading measure(int8_t led);  // LEDController::NONE for a dark reading

 private:
  bool sensorsReady(const Send& send);
  static String values(const Reading& r);
  LEDController& leds_;
  RGBSensor& rgb_;
  LuxSensor& lux_;
};
