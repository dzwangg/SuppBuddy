// SuppBuddy BLE test stub for a bare ESP32: no sensors needed. Sends fake readings in protocol v3 so the
// iPhone app and backend can be tested before the optics are wired. The real firmware lives in
// firmware/SupplementOpticalTester and speaks exactly the same protocol (repo README, "BLE contract").
//
//   "b"             -> I (settings), D (dark), B,<led> for W/R/G/B (water blank), E
//   "s"             -> I, then per ~1.4 s cycle: K (dark) and S,<t_ms>,<led> for W/R/G/B; E after RUN_SECONDS
//   "L|line1|line2" -> show text on the tester's screen (no reply)
// Values on every reading line: r,g,b,c (TCS34725, transmitted) then full,ir (TSL2591, scattered at 90 deg).
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLE2902.h>
#include <math.h>

#define SERVICE_UUID "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define RX_UUID      "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  // app -> ESP32
#define TX_UUID      "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  // ESP32 -> app

const int RUN_SECONDS = 30;
const char LEDS[4] = {'W', 'R', 'G', 'B'};
const float WAVELENGTH[4] = {525, 625, 525, 465};  // nm; white treated like green for scatter

// Fake optics (r, g, b, c, full, ir). Kept under the TCS34725's 21,504 ceiling at 50 ms.
const float DARK[6] = {300, 320, 280, 900, 40, 20};
const float BLANK[4][6] = {
  {6000, 7000, 5000, 18855, 400, 30},  // W
  {5200, 600, 300, 6500, 380, 28},     // R
  {700, 6200, 900, 8200, 390, 27},     // G
  {300, 1100, 5600, 7400, 360, 26},    // B
};
// A sample that dissolves like vitamin C: final absorbance per channel, cloudiness right after mixing
// (S_PEAK) settling to S_FINAL with time constant TAU, and scatter color exponent (fine particles ~ 1-4).
const float A[3] = {0.01, 0.01, 0.03}, S_PEAK = 2.5, S_FINAL = 1.1, TAU = 5, SCATTER_EXP = 1.5;

BLECharacteristic *tx;
BLEServer *server;
volatile char command = 0;
String screenText;

void send(const String &line) {
  tx->setValue((uint8_t *)line.c_str(), line.length());
  tx->notify();
  Serial.print(line);
  delay(15);  // let the BLE stack drain before the next notification
}

String values(const float v[6]) {
  String s;
  for (int i = 0; i < 6; i++) s += "," + String(v[i], i < 4 ? 1 : 0);
  return s;
}

void fakeDark(float out[6]) {
  for (int i = 0; i < 6; i++) out[i] = DARK[i] + random(-3, 4);
}

// t < 0 is the water blank.
void fakeLit(int led, float t, float out[6]) {
  const float *blank = BLANK[led];
  float frac = t < 0 ? 0 : 1 - expf(-t / TAU);
  float trans = 0;
  for (int k = 0; k < 3; k++) {
    float tk = powf(10, -A[k] * frac);
    out[k] = DARK[k] + (blank[k] - DARK[k]) * tk + random(-25, 26);
    trans += tk / 3;
  }
  out[3] = DARK[3] + (blank[3] - DARK[3]) * trans;
  float excess = t < 0 ? 0 : (S_FINAL - 1) + (S_PEAK - S_FINAL) * expf(-t / TAU);
  excess *= powf(525.0f / WAVELENGTH[led], SCATTER_EXP);
  out[4] = DARK[4] + (blank[4] - DARK[4]) * (1 + excess) + random(-4, 5);
  out[5] = blank[5] + random(-2, 3);
}

class RxCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    String v = c->getValue();
    if (v.length() == 0) return;
    if (v[0] == 'L') screenText = v;
    command = v[0];
  }
};

class ServerCallbacks : public BLEServerCallbacks {
  void onDisconnect(BLEServer *) override { BLEDevice::startAdvertising(); }
};

void setup() {
  Serial.begin(115200);
  BLEDevice::init("SuppBuddy");
  BLEDevice::setMTU(185);  // each line must fit in one notification
  server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());
  BLEService *service = server->createService(SERVICE_UUID);
  tx = service->createCharacteristic(TX_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  tx->addDescriptor(new BLE2902());
  service->createCharacteristic(RX_UUID, BLECharacteristic::PROPERTY_WRITE)->setCallbacks(new RxCallbacks());
  service->start();
  BLEDevice::getAdvertising()->addServiceUUID(SERVICE_UUID);
  BLEDevice::getAdvertising()->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.println("SuppBuddy stub (protocol v3) advertising");
}

void loop() {
  char c = command;
  if (!c) { delay(10); return; }
  command = 0;
  float v[6];
  const String info = "I,v3,4,50,25,100,WRGB\n";
  if (c == 'b') {
    send(info);
    fakeDark(v); send("D" + values(v) + "\n");
    for (int i = 0; i < 4; i++) { fakeLit(i, -1, v); send(String("B,") + LEDS[i] + values(v) + "\n"); }
    send("E\n");
  } else if (c == 's') {
    send(info);
    unsigned long start = millis();
    unsigned long cycleStart = 0;
    // like the tester: the last cycle starts at or after RUN_SECONDS, and a disconnect ends the run
    while (cycleStart < RUN_SECONDS * 1000UL && server->getConnectedCount() > 0) {
      cycleStart = millis() - start;
      fakeDark(v);
      send("K," + String(cycleStart) + values(v) + "\n");
      delay(270);
      for (int i = 0; i < 4; i++) {
        unsigned long t = millis() - start;
        fakeLit(i, t / 1000.0f, v);
        send("S," + String(t) + "," + LEDS[i] + values(v) + "\n");
        delay(270);  // the real tester takes ~285 ms per reading
      }
    }
    send("E\n");
  } else if (c == 'L') {
    Serial.print("screen: ");
    Serial.println(screenText.substring(2));  // real firmware: draw on the display
  }
  command = 0;  // like the tester: a command that arrived mid-run is stale, don't run it now
}
