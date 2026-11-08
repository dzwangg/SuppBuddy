// Logic self-check, runs on the Mac without Xcode tests:
//   swiftc SuppBuddy/Analysis.swift SuppBuddy/Server.swift SuppBuddy/NIH.swift checks/main.swift -o /tmp/suppbuddy-check && /tmp/suppbuddy-check
// Run from the repo root (it reads checks/fixtures/, which are real responses captured from the backend).
import Foundation

func near(_ a: Double, _ b: Double) -> Bool { abs(a - b) < 1e-9 }
func fixture(_ name: String) throws -> Data { try Data(contentsOf: URL(fileURLWithPath: "checks/fixtures/\(name)")) }

// BLE line framing: Arduino println sends "\r\n", chunks can split a line.
var buf = "D,300,320,280,900,40\r\nB,18000,22"
precondition(takeLines(&buf) == ["D,300,320,280,900,40"] && buf == "B,18000,22")
buf += "000,15000,55000,400\n\n"
precondition(takeLines(&buf) == ["B,18000,22000,15000,55000,400"] && buf.isEmpty)

// Protocol v3 lines (what firmware/SupplementOpticalTester sends).
precondition(DeviceLine("I,v3,4,50,25,100,WRGB") == .info(DeviceInfo(version: "v3", tcsGain: 4, tcsIntegrationMs: 50, tslGain: 25, tslIntegrationMs: 100, leds: "WRGB")))
precondition(DeviceLine("D,300.0,320.3,280.0,900.7,40,20") == .dark(Snapshot(r: 300, g: 320.3, b: 280, c: 900.7, scatter: 40, ir: 20)))
precondition(DeviceLine("B,R,5200.0,600.0,300.0,6500.0,380,28") == .blank(led: "r", Snapshot(r: 5200, g: 600, b: 300, c: 6500, scatter: 380, ir: 28)))
precondition(DeviceLine("K,1430,301,321,279,901,41,20") == .sample(Sample(t_ms: 1430, r: 301, g: 321, b: 279, c: 901, scatter: 41, ir: 20, led: "off")))
precondition(DeviceLine("S,1715,W,5900.5,6900,4950,18500,410,30") == .sample(Sample(t_ms: 1715, r: 5900.5, g: 6900, b: 4950, c: 18500, scatter: 410, ir: 30, led: "white")))
precondition(DeviceLine("S,2000,B,300,1100,5600,7400,360,26") == .sample(Sample(t_ms: 2000, r: 300, g: 1100, b: 5600, c: 7400, scatter: 360, ir: 26, led: "b")))
precondition(DeviceLine("X,TSL2591 not detected on GPIO 16/17. Check its wiring, then reset the tester.") ==
             .failure("TSL2591 not detected on GPIO 16/17. Check its wiring, then reset the tester."))
precondition(DeviceLine("E") == .end)
// Protocol v2 lines (older stubs: white light only) still parse.
let dark = Snapshot(r: 300, g: 320, b: 280, c: 900, scatter: 40)
let blank = Snapshot(r: 18000, g: 22000, b: 15000, c: 55000, scatter: 400)
precondition(DeviceLine("D,300,320,280,900,40") == .dark(dark))
precondition(DeviceLine("B, 18000, 22000, 15000, 55000, 400") == .blank(led: "white", blank))
precondition(DeviceLine("S,2000,1800,2200,1500,5500,760") == .sample(Sample(t_ms: 2000, r: 1800, g: 2200, b: 1500, c: 5500, scatter: 760)))
for bad in ["m", ",", "S,1,2,3", "D,1,2,x,4,5", "B,1,2,3,4,5,6", "123", "B,Y,1,2,3,4,5,6", "S,1,Q,1,2,3,4,5,6", "K,1,2,3", "I,v3,4,50", "E,1",
            // non-finite or huge numbers parse as Doubles; Int(nan) and Int(1e30) used to trap the app
            "S,nan,W,1,2,3,4,5,6", "S,1e30,W,1,2,3,4,5,6", "K,inf,1,2,3,4,5,6", "S,-5,W,1,2,3,4,5,6", "D,1,2,nan,4,5,6", "S,2000,1800,inf,1500,5500,760"] {
    precondition(DeviceLine(bad) == nil, bad)
}

// Live chart math matches the backend's formulas.
let clear = livePoint(Sample(t_ms: 1500, r: 18000, g: 22000, b: 15000, c: 0, scatter: 400), dark: dark, blank: blank)!
precondition(near(clear.seconds, 1.5) && near(clear.absorbance, 0) && near(clear.cloudiness, 1))
let tenth = Sample(t_ms: 0, r: 300 + 1770, g: 320 + 2168, b: 280 + 1472, c: 0, scatter: 40 + 720)
let p = livePoint(tenth, dark: dark, blank: blank)!
precondition(near(p.absorbance, 1) && near(p.cloudiness, 2)) // 10% transmission = absorbance 1; scatter 2x water
precondition(livePoint(tenth, dark: dark, blank: dark) == nil) // dead LED: blank equals dark

// Readings encode with the exact keys the backend expects.
let info = DeviceInfo(version: "v3", tcsGain: 4, tcsIntegrationMs: 50, tslGain: 25, tslIntegrationMs: 100, leds: "WRGB")
let set = BlankSet(info: info, dark: dark, blanks: ["white": blank, "r": blank, "g": blank, "b": blank])
let cycleSamples = [Sample(t_ms: 0, r: 1, g: 2, b: 3, c: 4, scatter: 5, ir: 6, led: "off"), Sample(t_ms: 285, r: 1, g: 2, b: 3, c: 4, scatter: 5, ir: 6)]
let readings = makeReadings(deviceID: "esp32-SuppBuddy", blank: set, samples: cycleSamples)
let json = try JSONSerialization.jsonObject(with: JSONEncoder().encode(readings)) as! [String: Any]
precondition(json["protocol"] as? String == "v3" && json["led_mode"] as? String == "cycle")
precondition(json["tcs_integration_ms"] as? Double == 50 && json["tsl_gain"] as? Double == 25)
precondition((json["blank"] as? [String: Any])?.keys.sorted() == ["b", "g", "r", "white"])
let firstSample = ((json["samples"] as? [[String: Any]])?.first)!
precondition(firstSample["t_ms"] as? Int == 0 && firstSample["led"] as? String == "off" && firstSample["ir"] as? Double == 6)
// A white-only tester (older stub) is sent as white mode.
let whiteOnly = makeReadings(deviceID: "x", blank: BlankSet(info: nil, dark: dark, blanks: ["white": blank]), samples: [Sample(t_ms: 0, r: 1, g: 2, b: 3, c: 4, scatter: 5)])
precondition(whiteOnly.led_mode == "white" && whiteOnly.protocol == "v1" && whiteOnly.tcs_gain == nil)
let darkJSON = try JSONSerialization.jsonObject(with: JSONEncoder().encode(dark)) as! [String: Any]
precondition(darkJSON["ir"] == nil) // nil fields are left out, not sent as null

// Sample prep and the confirm answer.
let prepJSON = try JSONSerialization.jsonObject(with: JSONEncoder().encode(SamplePrep(mass_mg: 500, volume_ml: 50, stirred: true))) as! [String: Any]
precondition(prepJSON["mass_mg"] as? Double == 500 && prepJSON["volume_ml"] as? Double == 50)
let held = try JSONDecoder().decode(ConfirmResult.self, from: Data(#"{"held": true, "n": 5, "reason": "doesn't match", "product_id": "x"}"#.utf8))
precondition(held.held == true && held.n == 5 && held.reason == "doesn't match")
let added = try JSONDecoder().decode(ConfirmResult.self, from: Data(#"{"held": false, "n": 6, "features": {}}"#.utf8))
precondition(added.held == false && added.n == 6)

// Real backend responses decode, and the progress feed reads them.
let warning = try JSONDecoder().decode(Scan.self, from: fixture("scan_warning.json"))
precondition(warning.report?.verdict == "WARNING" && warning.report?.accuracy.label == "inconsistent")
precondition(warning.qc?.series?.absorbance?.count == 60 && warning.lcd.code == "WARNING")
let feed = Server.steps(for: warning).map(\.text)
precondition(feed.contains("Verdict WARNING, set by the measurements and records"), "\(feed)")
precondition(feed.contains { $0.hasPrefix("Public records: FDA tainted list skipped") }, "\(feed)")
precondition(feed.last == "Explanation skipped (no ANTHROPIC_API_KEY)", "\(feed)")
let labelOnly = try JSONDecoder().decode(Scan.self, from: fixture("scan_label_only.json"))
precondition(labelOnly.report?.verdict == "NO_REF" && labelOnly.qc == nil)
// A scan that failed QC sends "series": {}; the app used to fail with "data is missing" on it.
let badScan = try JSONDecoder().decode(Scan.self, from: fixture("scan_bad_scan.json"))
precondition(badScan.report?.verdict == "BAD_SCAN" && badScan.qc?.series?.absorbance == nil && badScan.lcd.code == "BAD_SCAN")

var partial = warning
partial.status = "partial"
partial.stages?["agent"] = nil
precondition(Server.steps(for: partial).last?.text == "Claude is writing the explanation…")
precondition(Server.errorText(Data(#"{"detail":"scan not found"}"#.utf8), status: 404) == "scan not found")

// History survives a save/load round trip; an unreadable file is set aside, not overwritten.
let dir = FileManager.default.temporaryDirectory.appending(path: "suppbuddy-check-\(UUID())")
try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
let file = dir.appending(path: "history.json")
let saved = TestRecord(date: Date(timeIntervalSince1970: 0), scan: warning, steps: [Step(icon: "sparkles", text: "hi")], thumbnail: nil)
History.save([saved], to: file)
let loaded = History.load(from: file)
precondition(loaded.count == 1 && loaded[0].id == saved.id && loaded[0].scan.report?.verdict == "WARNING")
try Data("not json".utf8).write(to: file)
precondition(History.load(from: file).isEmpty)
let leftovers = try FileManager.default.contentsOfDirectory(atPath: dir.path)
precondition(leftovers.contains { $0.hasPrefix("history.json.bak-") })
try? FileManager.default.removeItem(at: dir)

// Barcodes: scanners give EAN-13 with a leading 0 for UPC-A; typos fail the check digit.
precondition(NIH.dsldFormat("0700580723633") == "7 00580 72363 3")
precondition(NIH.dsldFormat("700580723634") == nil) // wrong check digit
precondition(NIH.dsldFormat("000000000000") == nil) // placeholder in some database entries
precondition(NIH.dsldFormat("12345") == nil)

print("all checks passed")
