#pragma once
#include <Arduino.h>
#include <Adafruit_TCS34725.h>
#include <Adafruit_TSL2591.h>

// Pins, sensor settings and timing for the classic 38-pin ESP32-WROOM-32 DevKit.
// The pin table in the repo root README must match this file.
namespace Config {
  // Both sensors use I2C address 0x29, so each gets its own bus.
  constexpr uint8_t RGB_SDA = 21;  // TCS34725: in line behind the cuvette (transmitted light)
  constexpr uint8_t RGB_SCL = 22;
  constexpr uint8_t LUX_SDA = 16;  // TSL2591: 90 degrees to the beam (scattered light)
  constexpr uint8_t LUX_SCL = 17;

  // Each LED: GPIO -> its own 330 ohm resistor -> LED anode; cathode -> GND.
  // As wired on the main board.
  constexpr uint8_t LED_WHITE = 27;
  constexpr uint8_t LED_RED = 33;
  constexpr uint8_t LED_GREEN = 25;
  constexpr uint8_t LED_BLUE = 26;

  // Sensor settings. The firmware reports them in the "I" line; the backend derives saturation
  // limits from them and warns when a scan used different settings than the reference data.
  constexpr uint8_t TCS_INTEGRATION = TCS34725_INTEGRATIONTIME_50MS;
  constexpr uint16_t TCS_INTEGRATION_MS = 50;
  constexpr tcs34725Gain_t TCS_GAIN = TCS34725_GAIN_4X;
  constexpr uint16_t TCS_GAIN_X = 4;
  constexpr tsl2591Gain_t TSL_GAIN = TSL2591_GAIN_MED;
  constexpr uint16_t TSL_GAIN_X = 25;
  constexpr tsl2591IntegrationTime_t TSL_INTEGRATION = TSL2591_INTEGRATIONTIME_100MS;
  constexpr uint16_t TSL_INTEGRATION_MS = 100;

  constexpr uint8_t TCS_AVERAGE = 3;     // TCS34725 integrations averaged per reading
  constexpr uint16_t LED_SETTLE_MS = 5;  // LED output is stable within microseconds; this is margin
  constexpr uint16_t RUN_SECONDS = 30;   // length of a sample run
  constexpr uint32_t PROMPT_TIMEOUT_MS = 60000;  // "Blank done"/"Run done" on the LCD revert to "Ready" after this
  constexpr uint32_t SERIAL_BAUD = 115200;
  constexpr const char* BLE_NAME = "SuppBuddy";
}
