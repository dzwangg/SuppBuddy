#pragma once
#include <Arduino.h>

// The four measurement LEDs, in the order a cycle lights them.
class LEDController {
 public:
  static constexpr uint8_t COUNT = 4;
  static constexpr int8_t NONE = -1;  // all LEDs off (dark reading)
  void begin();
  void allOff();
  void onOnly(int8_t index);  // NONE turns everything off
  const char* name(uint8_t index) const;
  char code(uint8_t index) const;  // protocol letter: W, R, G, B
};
