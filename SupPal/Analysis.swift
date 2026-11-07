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

/// One line from the tester (protocol v2, see README "BLE contract").
enum DeviceLine: Equatable {
    case dark(Snapshot)  // D,r,g,b,c,scatter
    case blank(Snapshot) // B,r,g,b,c,scatter
    case sample(Sample)  // S,t_ms,r,g,b,c,scatter
    case end             // E

    init?(_ line: String) {
        let parts = line.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
        let nums = parts.dropFirst().compactMap(Double.init)
        guard nums.count == parts.count - 1 else { return nil } // every field after the tag must be a number
        switch (parts.first ?? "", nums.count) {
        case ("E", 0): self = .end
        case ("D", 5): self = .dark(Snapshot(r: nums[0], g: nums[1], b: nums[2], c: nums[3], scatter: nums[4]))
        case ("B", 5): self = .blank(Snapshot(r: nums[0], g: nums[1], b: nums[2], c: nums[3], scatter: nums[4]))
        case ("S", 6): self = .sample(Sample(t_ms: Int(nums[0]), r: nums[1], g: nums[2], b: nums[3], c: nums[4], scatter: nums[5]))
        default: return nil
        }
    }
}

/// Live chart point, using the backend's formulas (app/sensors/features.py):
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
