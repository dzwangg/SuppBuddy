#include "Measurements.h"
#include "Config.h"
#include <math.h>

Measurements::Measurements(LEDController& leds, RGBSensor& rgb, LuxSensor& lux)
  : leds_(leds), rgb_(rgb), lux_(lux) {}

void Measurements::csvHeader() {
  Serial.println("timestamp_ms,led,rgb_guess,rgb_dark_r,rgb_dark_g,rgb_dark_b,rgb_dark_clear,rgb_on_r,rgb_on_g,rgb_on_b,rgb_on_clear,rgb_delta_r,rgb_delta_g,rgb_delta_b,rgb_delta_clear,tsl_dark_full,tsl_dark_ir,tsl_on_full,tsl_on_ir,tsl_on_visible,tsl_on_lux,tsl_dark_lux,tsl_lux_change");
}

void Measurements::sweepRGB() { sweep(true, false, false); }
void Measurements::sweepLux() { sweep(false, true, false); }
void Measurements::sweepCombinedCSV() { sweep(true, true, true); }

void Measurements::sweep(bool needRgb, bool needLux, bool csv) {
  const bool useRgb = needRgb && rgb_.available();
  const bool useLux = needLux && lux_.available();
  if (!useRgb && !useLux) {
    leds_.allOff();
    Serial.println("Requested sensor(s) unavailable. Check wiring; reset ESP32 after fixing.");
    delay(1000);
    return;
  }

  for (uint8_t i = 0; i < LEDController::COUNT; ++i) {
    leds_.allOff();
    delay(Config::SETTLE_MS);
    RGBReading rgbDark, rgbOn, rgbDelta;
    LuxReading luxDark, luxOn;
    if (useRgb) rgbDark = rgb_.read();
    if (useLux) luxDark = lux_.read();

    leds_.onOnly(i);
    delay(Config::SETTLE_MS);
    if (useRgb) {
      rgbOn = rgb_.read();
      rgbDelta = RGBSensor::difference(rgbOn, rgbDark);
    }
    if (useLux) luxOn = lux_.read();
    leds_.allOff();

    if (csv) {
      Serial.print(millis()); Serial.print(',');
      Serial.print(leds_.name(i)); Serial.print(',');
      if (useRgb) {
        Serial.print(RGBSensor::approximateColor(rgbDelta)); Serial.print(',');
        Serial.print(rgbDark.red); Serial.print(',');
        Serial.print(rgbDark.green); Serial.print(',');
        Serial.print(rgbDark.blue); Serial.print(',');
        Serial.print(rgbDark.clear); Serial.print(',');
        Serial.print(rgbOn.red); Serial.print(',');
        Serial.print(rgbOn.green); Serial.print(',');
        Serial.print(rgbOn.blue); Serial.print(',');
        Serial.print(rgbOn.clear); Serial.print(',');
        Serial.print(rgbDelta.red); Serial.print(',');
        Serial.print(rgbDelta.green); Serial.print(',');
        Serial.print(rgbDelta.blue); Serial.print(',');
        Serial.print(rgbDelta.clear);
      } else {
        // 13 empty RGB fields, including the color guess.
        for (uint8_t k=0; k<13; ++k) Serial.print(',');
      }
      Serial.print(',');
      if (useLux) {
        Serial.print(luxDark.full); Serial.print(',');
        Serial.print(luxDark.infrared); Serial.print(',');
        Serial.print(luxOn.full); Serial.print(',');
        Serial.print(luxOn.infrared); Serial.print(',');
        Serial.print(luxOn.visible); Serial.print(',');
        if (luxOn.valid) Serial.print(luxOn.lux, 3);
        Serial.print(',');
        if (luxDark.valid) Serial.print(luxDark.lux, 3);
        Serial.print(',');
        if (luxOn.valid && luxDark.valid) Serial.print(luxOn.lux - luxDark.lux, 3);
      } else {
        // Eight missing TSL fields: one comma was already printed above.
        for (uint8_t k = 0; k < 7; ++k) Serial.print(',');
      }
      Serial.println();
    } else {
      Serial.print("\n--- LED: "); Serial.print(leds_.name(i)); Serial.println(" ---");
      if (useRgb) {
        Serial.print("Approx detected color: ");
        Serial.println(RGBSensor::approximateColor(rgbDelta));
        Serial.print("RGB+C LED-on counts: ");
        Serial.print(rgbOn.red); Serial.print(", ");
        Serial.print(rgbOn.green); Serial.print(", ");
        Serial.print(rgbOn.blue); Serial.print(", ");
        Serial.println(rgbOn.clear);
        Serial.print("RGB+C LED-off counts: ");
        Serial.print(rgbDark.red); Serial.print(", ");
        Serial.print(rgbDark.green); Serial.print(", ");
        Serial.print(rgbDark.blue); Serial.print(", ");
        Serial.println(rgbDark.clear);
        Serial.print("RGB+C corrected change: ");
        Serial.print(rgbDelta.red); Serial.print(", ");
        Serial.print(rgbDelta.green); Serial.print(", ");
        Serial.print(rgbDelta.blue); Serial.print(", ");
        Serial.println(rgbDelta.clear);
      }
      if (useLux) {
        Serial.print("TSL full / IR / visible counts: ");
        Serial.print(luxOn.full); Serial.print(" / ");
        Serial.print(luxOn.infrared); Serial.print(" / ");
        Serial.println(luxOn.visible);
        Serial.print("TSL LED-on lux: ");
        if (luxOn.valid) Serial.println(luxOn.lux, 3);
        else Serial.println("INVALID / SATURATED");
        Serial.print("TSL LED-off lux: ");
        if (luxDark.valid) Serial.println(luxDark.lux, 3);
        else Serial.println("INVALID / SATURATED");
        Serial.print("TSL LED-only lux change: ");
        if (luxDark.valid && luxOn.valid)
          Serial.println(luxOn.lux - luxDark.lux, 3);
        else Serial.println("N/A");
      }
    }
    delay(Config::BETWEEN_LIGHTS_MS);
  }
}

void Measurements::ambient() {
  leds_.allOff();
  if (rgb_.available()) {
    RGBReading r = rgb_.read();
    Serial.print("Ambient TCS R,G,B,C: ");
    Serial.print(r.red); Serial.print(",");
    Serial.print(r.green); Serial.print(",");
    Serial.print(r.blue); Serial.print(",");
    Serial.println(r.clear);
  } else Serial.println("Ambient TCS: NOT DETECTED");
  if (lux_.available()) {
    LuxReading l = lux_.read();
    Serial.print("Ambient TSL full/IR/visible: ");
    Serial.print(l.full); Serial.print("/");
    Serial.print(l.infrared); Serial.print("/");
    Serial.println(l.visible);
    Serial.print("Ambient TSL lux: ");
    if (l.valid) Serial.println(l.lux, 3);
    else Serial.println("INVALID / SATURATED");
  } else Serial.println("Ambient TSL: NOT DETECTED");
}
