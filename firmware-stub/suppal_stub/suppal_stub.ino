// SupPal BLE test stub for a bare ESP32: no sensors needed. Sends fake readings in protocol v2
// so the iPhone app and backend can be tested before the optics are wired.
//
// Protocol v2 (README, "BLE contract"): Nordic UART Service. The app writes a command to RX,
// the ESP32 answers with "\n"-terminated lines on TX.
//   "b"            -> "D,r,g,b,c,scatter"  LEDs off (dark)
//                     "B,r,g,b,c,scatter"  white LED on, cuvette holds clean water (blank)
//   "s"            -> "S,t_ms,r,g,b,c,scatter" once per second for RUN_SECONDS, then "E"
//   "L|line1|line2"-> show text on the tester's screen (no reply)
// r,g,b,c: raw TCS34725 counts (transmission, 180 deg). scatter: raw TSL2591 counts (90 deg).
//
// Real firmware, per the wiring schematic: TCS34725 on Wire (SDA 21, SCL 22), TSL2591 on a second
// bus Wire1 (SDA 16, SCL 17) because both use address 0x29, RGB LED (common cathode) on 25/26/27.
// Replace fakeRead() with real sensor reads; keep gain and integration time fixed between runs.
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLE2902.h>
#include <math.h>

#define SERVICE_UUID "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define RX_UUID      "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  // app -> ESP32
#define TX_UUID      "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  // ESP32 -> app

const int RUN_SECONDS = 60;
// Fake optics: dark counts, water blank counts, and a sample that dissolves like vitamin C
// (absorbance A per channel at the end, cloudiness S times the water reading, time constant TAU).
const float DARK[5]  = {300, 320, 280, 900, 40};
const float BLANK[5] = {18000, 22000, 15000, 55000, 400};
const float A[3] = {0.01, 0.01, 0.03}, S = 1.1, TAU = 5;

BLECharacteristic *tx;
volatile char command = 0;
String screenText;

void send(const String &line) {
  tx->setValue(line.c_str());
  tx->notify();
  delay(20);  // let the BLE stack drain before the next notification
}

String row(char tag, const float v[5]) {
  String s(tag);
  for (int i = 0; i < 5; i++) s += "," + String(v[i], 1);
  return s + "\n";
}

// t < 0 means "LEDs off".
void fakeRead(float t, bool ledOn, float out[5]) {
  if (!ledOn) { for (int i = 0; i < 5; i++) out[i] = DARK[i] + random(-5, 6); return; }
  float frac = t < 0 ? 0 : 1 - expf(-t / TAU);
  for (int i = 0; i < 3; i++) out[i] = DARK[i] + (BLANK[i] - DARK[i]) * powf(10, -A[i] * frac) + random(-25, 26);
  out[3] = DARK[3] + (out[0] - DARK[0] + out[1] - DARK[1] + out[2] - DARK[2]) * 1.05;
  out[4] = DARK[4] + (BLANK[4] - DARK[4]) * (1 + (S - 1) * frac) + random(-4, 5);
}

class RxCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    String v = c->getValue();
    if (v.length() == 0) return;
    if (v[0] == 'L') { screenText = v; command = 'L'; }
    else command = v[0];
  }
};

class ServerCallbacks : public BLEServerCallbacks {
  void onDisconnect(BLEServer *) override { BLEDevice::startAdvertising(); }
};

void setup() {
  Serial.begin(115200);
  BLEDevice::init("SupPal");
  BLEDevice::setMTU(185);  // each line must fit in one notification
  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());
  BLEService *service = server->createService(SERVICE_UUID);
  tx = service->createCharacteristic(TX_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  tx->addDescriptor(new BLE2902());
  service->createCharacteristic(RX_UUID, BLECharacteristic::PROPERTY_WRITE)->setCallbacks(new RxCallbacks());
  service->start();
  BLEDevice::getAdvertising()->addServiceUUID(SERVICE_UUID);
  BLEDevice::getAdvertising()->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.println("SupPal stub v2 advertising");
}

void loop() {
  char c = command;
  if (!c) { delay(10); return; }
  command = 0;
  float v[5];
  if (c == 'b') {
    fakeRead(0, false, v); send(row('D', v));
    fakeRead(-1, true, v); send(row('B', v));
    Serial.println("sent dark + blank");
  } else if (c == 's') {
    Serial.println("sample run started");
    for (int i = 0; i < RUN_SECONDS; i++) {
      fakeRead(i, true, v);
      String line = "S," + String(i * 1000);
      for (int k = 0; k < 5; k++) line += "," + String(v[k], 1);
      send(line + "\n");
      delay(1000);
    }
    send("E\n");
    Serial.println("sample run done");
  } else if (c == 'L') {
    Serial.print("screen: ");
    Serial.println(screenText.substring(2));  // real firmware: draw on the display
  }
}
