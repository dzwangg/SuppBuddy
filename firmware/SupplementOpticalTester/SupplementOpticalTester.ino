#include <Wire.h>
#include "Config.h"
#include "LEDController.h"
#include "RGBSensor.h"
#include "LuxSensor.h"
#include "Measurements.h"

// Single Arduino sketch. Different features live in their own .h/.cpp files.
// Both optical sensors use I2C address 0x29, so each has its own bus.
TwoWire LuxWire(1);
LEDController leds;
RGBSensor rgb;
LuxSensor lux;
Measurements measurements(leds, rgb, lux);

enum class Mode { LED, ALL_ON, OFF, RGB, LUX, SCAN, AMBIENT };
Mode mode = Mode::LED;  // LEDs chase at startup; use Serial Monitor to switch.

void help() {
  Serial.println("\n=== Supplement Optical Tester ===");
  Serial.println("Type a command, then press Enter (115200 baud):");
  Serial.println("  led     - flash five LEDs one after another");
  Serial.println("  on      - turn all five LEDs on");
  Serial.println("  off     - turn all five LEDs off (idle)");
  Serial.println("  rgb     - TCS34725 + five-LED color/intensity sweep");
  Serial.println("  lux     - TSL2591 + five-LED light-intensity sweep");
  Serial.println("  scan    - both sensors + CSV output for all five LEDs");
  Serial.println("  ambient - measure both sensors with LEDs off");
  Serial.println("  status  - print detected sensors");
  Serial.println("  help    - show commands");
}

void status() {
  Serial.print("TCS34725 on GPIO21/22: ");
  Serial.println(rgb.available() ? "DETECTED" : "NOT DETECTED");
  Serial.print("TSL2591 on GPIO16/17: ");
  Serial.println(lux.available() ? "DETECTED" : "NOT DETECTED");
}

void readCommand() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toLowerCase();
  if (cmd.length() == 0) return;

  leds.allOff();
  if      (cmd == "led") mode = Mode::LED;
  else if (cmd == "on") mode = Mode::ALL_ON;
  else if (cmd == "off") mode = Mode::OFF;
  else if (cmd == "rgb") mode = Mode::RGB;
  else if (cmd == "lux") mode = Mode::LUX;
  else if (cmd == "scan") {
    mode = Mode::SCAN;
    measurements.csvHeader();
  }
  else if (cmd == "ambient") mode = Mode::AMBIENT;
  else if (cmd == "status") status();
  else if (cmd == "help") help();
  else Serial.println("Unknown command. Type help.");
}

void setup() {
  Serial.begin(Config::SERIAL_BAUD);
  Serial.setTimeout(75);
  delay(500);
  leds.begin();

  Wire.begin(Config::RGB_SDA, Config::RGB_SCL);
  Wire.setClock(100000);
  LuxWire.begin(Config::LUX_SDA, Config::LUX_SCL);
  LuxWire.setClock(100000);

  rgb.begin(Wire);       // Failing to detect one sensor won't block other modes.
  lux.begin(LuxWire);
  status();
  help();
  Serial.println("Default mode: led");
}

void loop() {
  readCommand();
  switch (mode) {
    case Mode::LED: {
      static uint8_t position = 0;
      leds.onOnly(position);
      Serial.print("LED ON: "); Serial.println(leds.name(position));
      delay(500);
      leds.allOff();
      delay(200);
      position = (position + 1) % LEDController::COUNT;
      break;
    }
    case Mode::ALL_ON: leds.allOn(); delay(100); break;
    case Mode::OFF: leds.allOff(); delay(100); break;
    case Mode::RGB: measurements.sweepRGB(); break;
    case Mode::LUX: measurements.sweepLux(); break;
    case Mode::SCAN: measurements.sweepCombinedCSV(); break;
    case Mode::AMBIENT: measurements.ambient(); delay(900); break;
  }
}
