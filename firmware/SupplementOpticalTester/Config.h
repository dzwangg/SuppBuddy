#pragma once
#include <Arduino.h>

// Pin assignments for the classic 38-pin ESP32-WROOM-32 DevKit.
// Each LED: GPIO -> 330 ohm resistor -> LED anode; cathode -> GND.
namespace Config {
  constexpr uint8_t RGB_SDA = 21;
  constexpr uint8_t RGB_SCL = 22;
  constexpr uint8_t LUX_SDA = 16;
  constexpr uint8_t LUX_SCL = 17;
  constexpr uint32_t SERIAL_BAUD = 115200;
  constexpr uint16_t BETWEEN_LIGHTS_MS = 150;
  constexpr uint16_t SETTLE_MS = 180;
}
