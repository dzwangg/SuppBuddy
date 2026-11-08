#pragma once
#include <Arduino.h>

// Bluetooth LE link to the iPhone app: Nordic UART Service (repo README, "BLE contract").
// The phone powers the tester over USB but talks to it over Bluetooth: iOS apps can't read an
// ESP32's USB serial port. The app writes a command to RX; lines come back as TX notifications.
class BleLink {
 public:
  void begin(const char* name);
  bool connected() const;
  // Returns the pending command letter (and its full text, for "L|line1|line2"), or 0 if none.
  char takeCommand(String& text);
  void send(const String& line);  // one '\n'-terminated line; fits one notification
};
