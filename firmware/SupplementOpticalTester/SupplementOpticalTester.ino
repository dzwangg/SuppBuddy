// SuppBuddy optical tester firmware, protocol v3 (repo README, "BLE contract").
// The iPhone powers the tester over USB and controls it over Bluetooth. The same commands work
// from Arduino's Serial Monitor (115200 baud, "Newline"), so the rig can be tested on a laptop.
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
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
LiquidCrystal_I2C* lcd = nullptr;  // 16x2 on Wire (GPIO 21/22) next to the TCS34725; stays null if none answers
uint32_t screenSince = 0;  // when something other than "Ready" went up on the LCD; 0 = showing Ready

void help() {
  Serial.println("\n=== SuppBuddy optical tester (protocol v3) ===");
  Serial.println("Type a command and press Enter (115200 baud, Newline):");
  Serial.println("  b       - dark + water-blank readings for each LED");
  Serial.println("  s       - sample run: a dark + W/R/G/B reading cycle for " + String(Config::RUN_SECONDS) + " s");
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
  Serial.print("TSL2591 on GPIO 16/17: ");
  Serial.println(lux.available() ? "DETECTED" : "NOT DETECTED");
  Serial.print("LCD on GPIO 21/22: ");
  Serial.println(lcd ? "DETECTED" : "NOT DETECTED");
  Serial.print("Bluetooth: ");
  Serial.println(ble.connected() ? "phone connected" : "advertising as SuppBuddy");
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

// One 16-character LCD line: printable ASCII only, padded so old text is overwritten without clear().
String fit(const String& s) {
  String out;
  for (unsigned i = 0; i < s.length() && out.length() < 16; i++) out += (s[i] >= 32 && s[i] <= 126) ? s[i] : ' ';
  while (out.length() < 16) out += ' ';
  return out;
}

void lcdShow(const String& line1, const String& line2) {
  if (!lcd) return;
  lcd->setCursor(0, 0);
  lcd->print(fit(line1));
  lcd->setCursor(0, 1);
  lcd->print(fit(line2));
}

void showOnScreen(const String& text) {
  // text is "L|line1|line2"
  int bar = text.indexOf('|', 2);
  String line1 = bar > 0 ? text.substring(2, bar) : text.substring(2);
  String line2 = bar > 0 ? text.substring(bar + 1) : "";
  Serial.println("SCREEN: " + line1 + " / " + line2);
  lcdShow(line1, line2);
  screenSince = millis();  // verdicts too: back to Ready after PROMPT_TIMEOUT_MS
}

// Runs one protocol command. Output always goes to Serial; it also goes to the phone when the phone
// asked. A run started from the phone stops early if the phone disconnects.
void handle(char command, const String& text, bool fromPhone) {
  Measurements::Send send = [fromPhone](const String& line) {
    Serial.print(line);
    if (fromPhone) ble.send(line);
  };
  switch (command) {
    case 'b':
      lcdShow("SuppBuddy", "Reading water...");
      measurements.blank(send);
      lcdShow("Blank done", "Add the sample");
      screenSince = millis();
      break;
    case 's': {
      const uint32_t start = millis();
      const uint32_t length = (uint32_t)Config::RUN_SECONDS * 1000;
      measurements.run(send, [fromPhone, start, length] {  // called once per ~1.4 s cycle
        uint32_t elapsed = millis() - start;
        lcdShow("Testing sample", "Keep still " + String(elapsed < length ? (length - elapsed + 999) / 1000 : 0) + "s");
        return !fromPhone || ble.connected();
      });
      lcdShow("Run done", "Tap Analyze");
      screenSince = millis();
      break;
    }
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
  leds.begin();

  Wire.begin(Config::RGB_SDA, Config::RGB_SCL);
  Wire.setClock(100000);
  LuxWire.begin(Config::LUX_SDA, Config::LUX_SCL);
  LuxWire.setClock(100000);
  rgb.begin(Wire);  // a missing sensor is reported to the app as an X line, not a crash
  lux.begin(LuxWire);
  for (uint8_t addr : {0x27, 0x3F}) {  // PCF8574T backpacks answer at 0x27, PCF8574AT at 0x3F
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      lcd = new LiquidCrystal_I2C(addr, 16, 2);
      lcd->init();
      lcd->backlight();
      break;
    }
  }
  lcdShow("SuppBuddy", "Ready");

  ble.begin(Config::BLE_NAME);
  status();
  help();
}

void loop() {
  if (screenSince && millis() - screenSince > Config::PROMPT_TIMEOUT_MS) {  // nobody followed up: back to idle
    lcdShow("SuppBuddy", "Ready");
    screenSince = 0;
  }
  String text;
  char command = ble.takeCommand(text);
  if (command) {
    handle(command, text, true);
    // A command that arrived while that ran (a retry after the phone gave up, a Serial Monitor key) would
    // start a run nobody is listening to, and its lines would land in the app's next command.
    if (ble.takeCommand(text)) Serial.println("Ignored a command sent while the tester was busy.");
    while (Serial.available()) Serial.read();
  }
  readSerial();
  delay(5);
}
