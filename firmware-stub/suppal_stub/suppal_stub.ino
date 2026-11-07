// SupPal BLE test stub for a bare ESP32: no sensor needed.
// Lets the iPhone app connect and "measure" so the BLE link can be tested before the optics exist.
// Contract (README, "BLE contract"): Nordic UART Service; app writes "m", ESP32 notifies "v1,v2,...\n".
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLE2902.h>

#define SERVICE_UUID "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define RX_UUID      "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  // app -> ESP32
#define TX_UUID      "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  // ESP32 -> app

BLECharacteristic *tx;
volatile bool measureRequested = false;

class RxCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    auto v = c->getValue();
    if (v.length() > 0 && v[0] == 'm') measureRequested = true;
  }
};

class ServerCallbacks : public BLEServerCallbacks {
  void onDisconnect(BLEServer *) override { BLEDevice::startAdvertising(); }
};

void setup() {
  Serial.begin(115200);
  BLEDevice::init("SupPal");
  BLEDevice::setMTU(185);  // one reading line must fit in a single notification
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
  Serial.println("SupPal stub advertising");
}

void loop() {
  if (!measureRequested) { delay(10); return; }
  measureRequested = false;
  // ponytail: fake readings. Replace with: LED on, read each sensor channel, LED off.
  String line;
  for (int i = 0; i < 8; i++) line += String(random(1000, 4000)) + (i < 7 ? "," : "\n");
  tx->setValue(line.c_str());
  tx->notify();
  Serial.print("sent ");
  Serial.print(line);
}
