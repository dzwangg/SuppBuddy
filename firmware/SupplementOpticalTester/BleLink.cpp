#include "BleLink.h"
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLE2902.h>

#define SERVICE_UUID "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define RX_UUID      "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  // app -> ESP32
#define TX_UUID      "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  // ESP32 -> app

namespace {
  BLECharacteristic* tx = nullptr;
  volatile bool isConnected = false;
  // The BLE callback runs on another task, so the command is handed over under a lock.
  portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
  char pending[96];
  volatile bool hasPending = false;

  class RxCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic* c) override {
      String v = c->getValue();
      if (v.length() == 0) return;
      size_t n = min((size_t)v.length(), sizeof(pending) - 1);
      portENTER_CRITICAL(&lock);
      memcpy(pending, v.c_str(), n);
      pending[n] = 0;
      hasPending = true;
      portEXIT_CRITICAL(&lock);
    }
  };

  class ServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer*) override { isConnected = true; }
    void onDisconnect(BLEServer*) override {
      isConnected = false;
      BLEDevice::startAdvertising();
    }
  };
}

void BleLink::begin(const char* name) {
  BLEDevice::init(name);
  BLEDevice::setMTU(185);  // every protocol line (under ~70 bytes) fits one notification
  BLEServer* server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());
  BLEService* service = server->createService(SERVICE_UUID);
  tx = service->createCharacteristic(TX_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  tx->addDescriptor(new BLE2902());
  service->createCharacteristic(RX_UUID, BLECharacteristic::PROPERTY_WRITE)->setCallbacks(new RxCallbacks());
  service->start();
  BLEDevice::getAdvertising()->addServiceUUID(SERVICE_UUID);
  BLEDevice::getAdvertising()->setScanResponse(true);
  BLEDevice::startAdvertising();
}

bool BleLink::connected() const { return isConnected; }

char BleLink::takeCommand(String& text) {
  char buf[sizeof(pending)];
  bool got = false;
  portENTER_CRITICAL(&lock);
  if (hasPending) {
    memcpy(buf, pending, sizeof(buf));
    hasPending = false;
    got = true;
  }
  portEXIT_CRITICAL(&lock);
  if (!got) return 0;
  text = String(buf);
  return buf[0];
}

void BleLink::send(const String& line) {
  if (!isConnected || tx == nullptr) return;
  tx->setValue((uint8_t*)line.c_str(), line.length());
  tx->notify();
  delay(10);  // let the BLE stack drain before the next notification
}
