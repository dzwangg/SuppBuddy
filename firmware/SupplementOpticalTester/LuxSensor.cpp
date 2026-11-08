#include "LuxSensor.h"
#include "Config.h"

LuxSensor::LuxSensor() : tsl_(2591) {}

bool LuxSensor::begin(TwoWire& bus) {
  bus_ = &bus;
  ready_ = tsl_.begin(&bus);
  if (ready_) {
    tsl_.setGain(Config::TSL_GAIN);
    tsl_.setTiming(Config::TSL_INTEGRATION);
  }
  return ready_;
}

bool LuxSensor::alive() {
  if (!ready_ || !bus_) return false;
  bus_->beginTransmission(TSL2591_ADDR);
  return bus_->endTransmission() == 0;
}

LuxReading LuxSensor::read() {
  LuxReading out;
  if (!ready_) return out;
  const uint32_t packed = tsl_.getFullLuminosity();
  out.full = (uint16_t)(packed & 0xFFFF);
  out.infrared = (uint16_t)(packed >> 16);
  return out;
}
