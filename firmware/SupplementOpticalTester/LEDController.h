#pragma once
#include <Arduino.h>

// All LED pin mapping and switching is implemented in one module.
class LEDController {
 public:
  static constexpr uint8_t COUNT = 5;
  void begin();
  void allOff();
  void allOn();
  void onOnly(uint8_t index);
  const char* name(uint8_t index) const;
};
