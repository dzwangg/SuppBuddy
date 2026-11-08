#include "Measurements.h"
#include "Config.h"

Measurements::Measurements(LEDController& leds, RGBSensor& rgb, LuxSensor& lux)
  : leds_(leds), rgb_(rgb), lux_(lux) {}

// "I,v3,<tcs gain>,<tcs ms>,<tsl gain>,<tsl ms>,<LED codes in cycle order>"
void Measurements::info(const Send& send) {
  String leds;
  for (uint8_t i = 0; i < LEDController::COUNT; ++i) leds += leds_.code(i);
  send("I,v3," + String(Config::TCS_GAIN_X) + "," + String(Config::TCS_INTEGRATION_MS) + "," +
       String(Config::TSL_GAIN_X) + "," + String(Config::TSL_INTEGRATION_MS) + "," + leds + "\n");
}

bool Measurements::sensorsReady(const Send& send) {
  if (!rgb_.available()) {
    send("X,TCS34725 not detected on GPIO 21/22. Check its wiring, then reset the tester.\n");
  } else if (!lux_.available()) {
    send("X,TSL2591 not detected on GPIO 16/17. Check its wiring and solder joints, then reset the tester.\n");
  } else {
    return true;
  }
  send("E\n");
  return false;
}

// One reading with one LED on (or none). The TSL2591 integration (~120 ms) runs first; meanwhile the
// TCS34725 keeps integrating under the same light, so its first register read is already valid.
Reading Measurements::measure(int8_t led) {
  leds_.onOnly(led);
  delay(Config::LED_SETTLE_MS);
  Reading out;
  out.lux = lux_.read();
  out.rgb = rgb_.readAveraged(Config::TCS_AVERAGE);
  leds_.allOff();
  return out;
}

// "r,g,b,c,full,ir": TCS34725 averages (one decimal), then TSL2591 counts.
String Measurements::values(const Reading& r) {
  return String(r.rgb.red, 1) + "," + String(r.rgb.green, 1) + "," + String(r.rgb.blue, 1) + "," +
         String(r.rgb.clear, 1) + "," + String(r.lux.full) + "," + String(r.lux.infrared);
}

void Measurements::blank(const Send& send) {
  if (!sensorsReady(send)) return;
  info(send);
  send("D," + values(measure(LEDController::NONE)) + "\n");
  for (uint8_t i = 0; i < LEDController::COUNT; ++i) {
    send(String("B,") + leds_.code(i) + "," + values(measure(i)) + "\n");
  }
  send("E\n");
}

void Measurements::run(const Send& send, const KeepGoing& keepGoing) {
  if (!sensorsReady(send)) return;
  info(send);
  const uint32_t start = millis();
  const uint32_t length = (uint32_t)Config::RUN_SECONDS * 1000;
  // Cycles run until one has started at or after RUN_SECONDS, so the readings span the whole run.
  uint32_t cycleStart = 0;
  while (cycleStart < length && keepGoing()) {
    // A dark reading every cycle lets the backend follow (and subtract) room light that drifts in.
    cycleStart = millis() - start;
    uint32_t t = cycleStart;
    send("K," + String(t) + "," + values(measure(LEDController::NONE)) + "\n");
    for (uint8_t i = 0; i < LEDController::COUNT; ++i) {
      t = millis() - start;
      send("S," + String(t) + "," + leds_.code(i) + "," + values(measure(i)) + "\n");
    }
  }
  leds_.allOff();
  send("E\n");
}
