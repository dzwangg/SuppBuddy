#include "LEDController.h"
#include "Config.h"

namespace {
  const uint8_t LED_PINS[LEDController::COUNT] = {
    Config::LED_WHITE, Config::LED_RED, Config::LED_GREEN, Config::LED_BLUE
  };
  const char* const LED_NAMES[LEDController::COUNT] = {"WHITE", "RED", "GREEN", "BLUE"};
  const char LED_CODES[LEDController::COUNT] = {'W', 'R', 'G', 'B'};
}

void LEDController::begin() {
  for (uint8_t i = 0; i < COUNT; ++i) pinMode(LED_PINS[i], OUTPUT);
  allOff();
}

void LEDController::allOff() {
  for (uint8_t i = 0; i < COUNT; ++i) digitalWrite(LED_PINS[i], LOW);
}

void LEDController::onOnly(int8_t index) {
  allOff();
  if (index >= 0 && index < COUNT) digitalWrite(LED_PINS[index], HIGH);
}

const char* LEDController::name(uint8_t index) const {
  return index < COUNT ? LED_NAMES[index] : "UNKNOWN";
}

char LEDController::code(uint8_t index) const {
  return index < COUNT ? LED_CODES[index] : '?';
}
