// Logic self-check, runs on the Mac without Xcode tests:
//   swiftc SupPal/Analysis.swift SupPal/Server.swift SupPal/NIH.swift checks/main.swift -o /tmp/suppal-check && /tmp/suppal-check
// Run from the repo root (it reads checks/fixtures/, which are real responses captured from the backend).
import Foundation

func near(_ a: Double, _ b: Double) -> Bool { abs(a - b) < 1e-9 }
func fixture(_ name: String) throws -> Data { try Data(contentsOf: URL(fileURLWithPath: "checks/fixtures/\(name)")) }

// BLE line framing: Arduino println sends "\r\n", chunks can split a line.
var buf = "D,300,320,280,900,40\r\nB,18000,22"
precondition(takeLines(&buf) == ["D,300,320,280,900,40"] && buf == "B,18000,22")
buf += "000,15000,55000,400\n\n"
precondition(takeLines(&buf) == ["B,18000,22000,15000,55000,400"] && buf.isEmpty)

// Protocol v2 lines.
let dark = Snapshot(r: 300, g: 320, b: 280, c: 900, scatter: 40)
let blank = Snapshot(r: 18000, g: 22000, b: 15000, c: 55000, scatter: 400)
precondition(DeviceLine("D,300,320,280,900,40") == .dark(dark))
precondition(DeviceLine("B, 18000, 22000, 15000, 55000, 400") == .blank(blank))
precondition(DeviceLine("S,2000,1800,2200,1500,5500,760") == .sample(Sample(t_ms: 2000, r: 1800, g: 2200, b: 1500, c: 5500, scatter: 760)))
precondition(DeviceLine("E") == .end)
for bad in ["m", ",", "S,1,2,3", "D,1,2,x,4,5", "B,1,2,3,4,5,6", "123"] { precondition(DeviceLine(bad) == nil, bad) }

// Live chart math matches the backend's formulas.
let clear = livePoint(Sample(t_ms: 1500, r: 18000, g: 22000, b: 15000, c: 0, scatter: 400), dark: dark, blank: blank)!
precondition(near(clear.seconds, 1.5) && near(clear.absorbance, 0) && near(clear.cloudiness, 1))
let tenth = Sample(t_ms: 0, r: 300 + 1770, g: 320 + 2168, b: 280 + 1472, c: 0, scatter: 40 + 720)
let p = livePoint(tenth, dark: dark, blank: blank)!
precondition(near(p.absorbance, 1) && near(p.cloudiness, 2)) // 10% transmission = absorbance 1; scatter 2x water
precondition(livePoint(tenth, dark: dark, blank: dark) == nil) // dead LED: blank equals dark

// Readings encode with the exact keys the backend expects.
let readings = DeviceReadings(device_id: "esp32-SupPal", dark: dark, blank: ["white": blank], samples: [Sample(t_ms: 0, r: 1, g: 2, b: 3, c: 4, scatter: 5)])
let json = try JSONSerialization.jsonObject(with: JSONEncoder().encode(readings)) as! [String: Any]
precondition(json["protocol"] as? String == "v1" && json["led_mode"] as? String == "white")
precondition((json["blank"] as? [String: Any])?["white"] != nil)
precondition(((json["samples"] as? [[String: Any]])?.first)?["t_ms"] as? Int == 0)

// Real backend responses decode, and the progress feed reads them.
let warning = try JSONDecoder().decode(Scan.self, from: fixture("scan_warning.json"))
precondition(warning.report?.verdict == "WARNING" && warning.report?.accuracy.label == "inconsistent")
precondition(warning.qc?.series?.absorbance.count == 60 && warning.lcd.code == "WARNING")
let feed = Server.steps(for: warning).map(\.text)
precondition(feed.contains("Verdict WARNING, set by the measurements and records"), "\(feed)")
precondition(feed.contains { $0.hasPrefix("Public records: FDA tainted list skipped") }, "\(feed)")
precondition(feed.last == "Explanation skipped (no ANTHROPIC_API_KEY)", "\(feed)")
let labelOnly = try JSONDecoder().decode(Scan.self, from: fixture("scan_label_only.json"))
precondition(labelOnly.report?.verdict == "NO_REF" && labelOnly.qc == nil)

var partial = warning
partial.status = "partial"
partial.stages?["agent"] = nil
precondition(Server.steps(for: partial).last?.text == "Claude is writing the explanation…")
precondition(Server.errorText(Data(#"{"detail":"scan not found"}"#.utf8), status: 404) == "scan not found")

// History survives a save/load round trip; an unreadable file is set aside, not overwritten.
let dir = FileManager.default.temporaryDirectory.appending(path: "suppal-check-\(UUID())")
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
