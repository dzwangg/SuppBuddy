#include "LEDController.h"

namespace {
  const uint8_t LED_PINS[LEDController::COUNT] = {25, 26, 32, 27, 33};
  const char* const LED_NAMES[LEDController::COUNT] = {
    "RED", "GREEN", "YELLOW", "BLUE", "WHITE"
  };
}

void LEDController::begin() {
  for (uint8_t i = 0; i < COUNT; ++i) {
    pinMode(LED_PINS[i], OUTPUT);
  }
  allOff();
}

void LEDController::allOff() {
  for (uint8_t i = 0; i < COUNT; ++i) {
    digitalWrite(LED_PINS[i], LOW);
  }
}

void LEDController::allOn() {
  for (uint8_t i = 0; i < COUNT; ++i) {
    digitalWrite(LED_PINS[i], HIGH);
  }
}

void LEDController::onOnly(uint8_t index) {
  allOff();
  if (index < COUNT) digitalWrite(LED_PINS[index], HIGH);
}

const char* LEDController::name(uint8_t index) const {
  return index < COUNT ? LED_NAMES[index] : "UNKNOWN";
}
