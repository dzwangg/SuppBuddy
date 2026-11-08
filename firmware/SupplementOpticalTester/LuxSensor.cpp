#include "LuxSensor.h"
#include <math.h>

LuxSensor::LuxSensor() : tsl_(2591) {}

bool LuxSensor::begin(TwoWire& bus) {
  ready_ = tsl_.begin(&bus);
  if (ready_) {
    // Medium gain helps small LED signals. Switch to LOW if readings saturate.
    tsl_.setGain(TSL2591_GAIN_MED);
    tsl_.setTiming(TSL2591_INTEGRATIONTIME_100MS);
  }
  return ready_;
}

LuxReading LuxSensor::read() {
  LuxReading result;
  if (!ready_) return result;
  const uint32_t packed = tsl_.getFullLuminosity();
  result.full = (uint16_t)(packed & 0xFFFF);
  result.infrared = (uint16_t)(packed >> 16);
  result.visible = (int32_t)result.full - (int32_t)result.infrared;
  const float estimate = tsl_.calculateLux(result.full, result.infrared);
  result.valid = isfinite(estimate) && estimate >= 0.0f;
  result.lux = result.valid ? estimate : NAN;
  return result;
}
