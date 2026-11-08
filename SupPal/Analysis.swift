import Foundation

struct AppError: LocalizedError {
    let errorDescription: String?
    init(_ message: String) { errorDescription = message }
}

/// Pulls complete lines out of the BLE receive buffer, leaving any partial line behind.
/// Uses `isNewline` because Swift treats "\r\n" (Arduino println) as one Character.
func takeLines(_ buffer: inout String) -> [String] {
    var lines: [String] = []
    while let nl = buffer.firstIndex(where: \.isNewline) {
        let line = buffer[..<nl].trimmingCharacters(in: .whitespaces)
        buffer.removeSubrange(...nl)
        if !line.isEmpty { lines.append(line) }
    }
    return lines
}

/// The tester's sensor settings, from its "I" line.
struct DeviceInfo: Equatable {
    var version: String
    var tcsGain, tcsIntegrationMs, tslGain, tslIntegrationMs: Double
    var leds: String // LED letters in cycle order, e.g. "WRGB"
}

/// One line from the tester (protocol v3, see README "BLE contract"). Every reading carries
/// r,g,b,c (TCS34725, transmitted) then full,ir (TSL2591, scattered at 90°).
///   I,v3,tcsGain,tcsMs,tslGain,tslMs,LEDS     settings
///   D,r,g,b,c,full,ir                         dark, with the blank
///   B,<W|R|G|B>,r,g,b,c,full,ir               water blank under one LED
///   K,t_ms,r,g,b,c,full,ir                    dark during the run
///   S,t_ms,<W|R|G|B>,r,g,b,c,full,ir          sample under one LED
///   E                                         end of a command
///   X,<message>                               the tester can't measure (e.g. a sensor isn't detected)
/// Protocol v2 lines (white light only, no ir) are still read, for older stubs.
enum DeviceLine: Equatable {
    case info(DeviceInfo)
    case dark(Snapshot)
    case blank(led: String, Snapshot)
    case sample(Sample) // led "off" for the dark readings taken during a run
    case end
    case failure(String)

    static let ledNames: [String: String] = ["W": "white", "R": "r", "G": "g", "B": "b"]

    init?(_ line: String) {
        let parts = line.split(separator: ",", omittingEmptySubsequences: false).map { $0.trimmingCharacters(in: .whitespaces) }
        guard let tag = parts.first, !tag.isEmpty else { return nil }
        let rest = Array(parts.dropFirst())

        /// All fields numeric, with the expected count.
        func numbers(_ fields: [String], count: [Int]) -> [Double]? {
            let nums = fields.compactMap(Double.init)
            return nums.count == fields.count && count.contains(nums.count) ? nums : nil
        }
        func snapshot(_ n: [Double]) -> Snapshot {
            Snapshot(r: n[0], g: n[1], b: n[2], c: n[3], scatter: n[4], ir: n.count > 5 ? n[5] : nil)
        }
        func sample(_ t: Double, _ n: [Double], led: String) -> Sample {
            Sample(t_ms: Int(t), r: n[0], g: n[1], b: n[2], c: n[3], scatter: n[4], ir: n.count > 5 ? n[5] : nil, led: led)
        }

        switch tag {
        case "E":
            guard rest.isEmpty else { return nil }
            self = .end
        case "X": // the message is free text and can contain commas
            let comma = line.firstIndex(of: ",") ?? line.endIndex
            self = .failure(line[comma...].dropFirst().trimmingCharacters(in: .whitespaces))
        case "I":
            guard rest.count == 6, let n = numbers(Array(rest[1...4]), count: [4]) else { return nil }
            self = .info(DeviceInfo(version: rest[0], tcsGain: n[0], tcsIntegrationMs: n[1], tslGain: n[2], tslIntegrationMs: n[3], leds: rest[5]))
        case "D":
            guard let n = numbers(rest, count: [5, 6]) else { return nil }
            self = .dark(snapshot(n))
        case "B":
            if let led = rest.first.flatMap({ Self.ledNames[$0] }), let n = numbers(Array(rest.dropFirst()), count: [6]) {
                self = .blank(led: led, snapshot(n))
            } else if let n = numbers(rest, count: [5]) { // v2: white only
                self = .blank(led: "white", snapshot(n))
            } else { return nil }
        case "K":
            guard let n = numbers(rest, count: [7]) else { return nil }
            self = .sample(sample(n[0], Array(n.dropFirst()), led: "off"))
        case "S":
            if rest.count == 8, let led = Self.ledNames[rest[1]], let t = Double(rest[0]), let n = numbers(Array(rest[2...]), count: [6]) {
                self = .sample(sample(t, n, led: led))
            } else if let n = numbers(rest, count: [6]) { // v2: S,t_ms,r,g,b,c,scatter under white light
                self = .sample(sample(n[0], Array(n.dropFirst()), led: "white"))
            } else { return nil }
        default:
            return nil
        }
    }
}

/// What "Measure blank" collects: the dark reading, the water blank under each LED, and the settings.
struct BlankSet: Equatable {
    var info: DeviceInfo?
    var dark: Snapshot
    var blanks: [String: Snapshot]
    var white: Snapshot? { blanks["white"] }
}

/// The payload the backend analyzes. Colored-LED blanks or readings mean protocol v3's cycle mode.
func makeReadings(deviceID: String, blank: BlankSet, samples: [Sample]) -> DeviceReadings {
    let cycle = blank.blanks.keys.contains { $0 != "white" } || samples.contains { $0.led != "white" }
    return DeviceReadings(device_id: deviceID, protocol: cycle ? "v3" : "v1", led_mode: cycle ? "cycle" : "white",
                          tcs_gain: blank.info?.tcsGain, tcs_integration_ms: blank.info?.tcsIntegrationMs,
                          tsl_gain: blank.info?.tslGain, tsl_integration_ms: blank.info?.tslIntegrationMs,
                          dark: blank.dark, blank: blank.blanks, samples: samples)
}

/// Live chart point for a white-light reading, using the backend's formulas (app/sensors/features.py):
///   absorbance = mean over R,G,B of -log10((I - dark) / (blank - dark))
///   cloudiness = (scatter - dark) / (blank - dark), so 1.0 means as clear as water.
func livePoint(_ s: Sample, dark: Snapshot, blank: Snapshot) -> (seconds: Double, absorbance: Double, cloudiness: Double)? {
    let channels = [(s.r, dark.r, blank.r), (s.g, dark.g, blank.g), (s.b, dark.b, blank.b)]
    guard channels.allSatisfy({ $0.2 > $0.1 }), blank.scatter > dark.scatter else { return nil }
    let a = channels.map { -log10(max(($0.0 - $0.1) / ($0.2 - $0.1), 1e-4)) }.reduce(0, +) / 3
    return (Double(s.t_ms) / 1000, a, (s.scatter - dark.scatter) / (blank.scatter - dark.scatter))
}

/// One finished test, saved on the phone.
struct TestRecord: Codable, Identifiable {
    var id = UUID()
    let date: Date
    var scan: Scan
    let steps: [Step]
    let thumbnail: Data? // small JPEG of the label, if one was photographed
}

/// Past tests as one JSON file in the app's Documents folder.
// ponytail: whole-file rewrite per save; fine for hundreds of tests, switch to SwiftData if it grows past that.
enum History {
    static let url = URL.documentsDirectory.appending(path: "history.json")

    static func load(from file: URL = url) -> [TestRecord] {
        guard let data = try? Data(contentsOf: file) else { return [] }
        if let records = try? JSONDecoder().decode([TestRecord].self, from: data) { return records }
        // Unreadable (e.g. the format changed): set it aside so the next save doesn't overwrite it.
        try? FileManager.default.moveItem(at: file, to: file.appendingPathExtension("bak-\(Int(Date().timeIntervalSince1970))"))
        return []
    }

    static func save(_ records: [TestRecord], to file: URL = url) {
        try? JSONEncoder().encode(records).write(to: file, options: .atomic)
    }
}
