// SupPal optical tester firmware, protocol v3 (repo README, "BLE contract").
// The iPhone powers the tester over USB and controls it over Bluetooth. The same commands work
// from Arduino's Serial Monitor (115200 baud, "Newline"), so the rig can be tested on a laptop.
#include <Wire.h>
#include "Config.h"
#include "LEDController.h"
#include "RGBSensor.h"
#include "LuxSensor.h"
#include "Measurements.h"
#include "BleLink.h"

// Both optical sensors use I2C address 0x29, so each has its own bus.
TwoWire LuxWire(1);
LEDController leds;
RGBSensor rgb;
LuxSensor lux;
Measurements measurements(leds, rgb, lux);
BleLink ble;

void help() {
  Serial.println("\n=== SupPal optical tester (protocol v3) ===");
  Serial.println("Type a command and press Enter (115200 baud, Newline):");
  Serial.println("  b       - dark + water-blank readings for each LED");
  Serial.println("  s       - sample run: a dark + W/R/G/B reading cycle for 60 s");
  Serial.println("  i       - sensor settings line");
  Serial.println("  status  - which sensors were detected");
  Serial.println("  led     - light each LED for half a second (wiring check)");
  Serial.println("  help    - this list");
  Serial.println("Lines: I=settings D=dark B=blank K=dark during run S=sample E=end X=error");
  Serial.println("Values: r,g,b,c (TCS34725 transmitted) then full,ir (TSL2591 scattered)");
}

void status() {
  Serial.print("TCS34725 on GPIO 21/22: ");
  Serial.println(rgb.available() ? "DETECTED" : "NOT DETECTED");
  Serial.print("TCS34725 white LED: held off by GPIO ");
  Serial.print(Config::TCS_LED_PIN);
  Serial.println(" (wire the board's LED pin there; if it still glows, check that wire)");
  Serial.print("TSL2591 on GPIO 16/17: ");
  Serial.println(lux.available() ? "DETECTED" : "NOT DETECTED");
  Serial.print("Bluetooth: ");
  Serial.println(ble.connected() ? "phone connected" : "advertising as SupPal");
}

void ledCheck() {
  for (uint8_t i = 0; i < LEDController::COUNT; ++i) {
    Serial.print("LED ON: ");
    Serial.println(leds.name(i));
    leds.onOnly(i);
    delay(500);
  }
  leds.allOff();
}

// TODO(lcd): draw on the tester's display once it's wired (16x2 assumed by the backend).
void showOnScreen(const String& text) {
  // text is "L|line1|line2"
  int bar = text.indexOf('|', 2);
  String line1 = bar > 0 ? text.substring(2, bar) : text.substring(2);
  String line2 = bar > 0 ? text.substring(bar + 1) : "";
  Serial.println("SCREEN: " + line1 + " / " + line2);
}

// Runs one protocol command. Output always goes to Serial; it also goes to the phone when the phone
// asked. A run started from the phone stops early if the phone disconnects.
void handle(char command, const String& text, bool fromPhone) {
  Measurements::Send send = [fromPhone](const String& line) {
    Serial.print(line);
    if (fromPhone) ble.send(line);
  };
  switch (command) {
    case 'b': measurements.blank(send); break;
    case 's': measurements.run(send, [fromPhone] { return !fromPhone || ble.connected(); }); break;
    case 'i': measurements.info(send); break;
    case 'L': showOnScreen(text); break;
    default: break;
  }
}

void readSerial() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd.length() == 0) return;
  String lower = cmd;
  lower.toLowerCase();
  if (lower == "status") status();
  else if (lower == "led") ledCheck();
  else if (lower == "help") help();
  else if (lower == "b" || lower == "s" || lower == "i") handle(lower[0], cmd, false);
  else if (cmd.startsWith("L|")) handle('L', cmd, false);
  else Serial.println("Unknown command. Type help.");
}

void setup() {
  Serial.begin(Config::SERIAL_BAUD);
  Serial.setTimeout(75);
  delay(300);
  RGBSensor::ledOff();  // first thing: the sensor board's white LED is on until this pin goes low
  leds.begin();

  Wire.begin(Config::RGB_SDA, Config::RGB_SCL);
  Wire.setClock(100000);
  LuxWire.begin(Config::LUX_SDA, Config::LUX_SCL);
  LuxWire.setClock(100000);
  rgb.begin(Wire);  // a missing sensor is reported to the app as an X line, not a crash
  lux.begin(LuxWire);

  ble.begin(Config::BLE_NAME);
  status();
  help();
}

void loop() {
  String text;
  char command = ble.takeCommand(text);
  if (command) handle(command, text, true);
  readSerial();
  delay(5);
}
