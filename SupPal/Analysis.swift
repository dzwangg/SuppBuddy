import Foundation

struct AppError: LocalizedError {
    let errorDescription: String?
    init(_ message: String) { errorDescription = message }
}

/// One crowdsourced reference spectrum (absorbance per sensor channel).
struct Reference: Codable {
    let product: String
    let absorbance: [Double]

    // ponytail: bundled demo data; swap for the team's crowdsourced DB once it exists.
    static let all: [Reference] = {
        guard let url = Bundle.main.url(forResource: "references", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return [] }
        return (try? JSONDecoder().decode([Reference].self, from: data)) ?? []
    }()
}

struct Match: Codable {
    let reference: Reference
    let similarity: Double
}

/// One finished test, saved on the phone.
struct TestRecord: Codable, Identifiable {
    var id = UUID()
    let date: Date
    let report: Report
    let spectrum: [Double]
    let match: Match?
    let steps: [Step]
    let thumbnail: Data // small JPEG of the label
    var official: OfficialLabel? = nil // NIH record for the scanned barcode; optional so older saved tests still load
}

/// Past tests as one JSON file in the app's Documents folder.
// ponytail: whole-file rewrite per save; fine for hundreds of tests, switch to SwiftData if it grows past that.
enum History {
    static let url = URL.documentsDirectory.appending(path: "history.json")

    static func load(from file: URL = url) -> [TestRecord] {
        guard let data = try? Data(contentsOf: file) else { return [] }
        if let records = try? JSONDecoder().decode([TestRecord].self, from: data) { return records }
        // Unreadable (e.g. the format changed): set it aside so the next save doesn't overwrite it.
        try? FileManager.default.moveItem(at: file, to: file.appendingPathExtension("bak"))
        return []
    }

    static func save(_ records: [TestRecord], to file: URL = url) {
        try? JSONEncoder().encode(records).write(to: file, options: .atomic)
    }
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

/// "512, 1033,2048" -> [512, 1033, 2048]; nil if any field isn't a number.
func parseReading(_ line: String) -> [Double]? {
    let values = line.split(separator: ",").map { Double($0.trimmingCharacters(in: .whitespacesAndNewlines)) }
    guard !values.isEmpty, !values.contains(nil) else { return nil }
    return values.compactMap { $0 }
}

/// Beer-Lambert absorbance per channel: A = -log10(sample / blank). nil if channel counts differ.
func absorbance(sample: [Double], blank: [Double]) -> [Double]? {
    guard sample.count == blank.count else { return nil }
    return zip(sample, blank).map { -log10(max($0, 1) / max($1, 1)) }
}

/// Cosine similarity (spectral angle): compares spectrum shape, ignores concentration.
// ponytail: shape-only match on a handful of channels; can't tell apart compounds with similar color.
func similarity(_ a: [Double], _ b: [Double]) -> Double {
    guard a.count == b.count else { return 0 }
    let dot = zip(a, b).map(*).reduce(0, +)
    let norms = sqrt(a.map { $0 * $0 }.reduce(0, +)) * sqrt(b.map { $0 * $0 }.reduce(0, +))
    return norms > 0 ? dot / norms : 0
}

func topMatches(_ spectrum: [Double], in refs: [Reference], k: Int = 3) -> [Match] {
    refs.map { Match(reference: $0, similarity: similarity(spectrum, $0.absorbance)) }
        .sorted { $0.similarity > $1.similarity }
        .prefix(k)
        .map { $0 }
}
