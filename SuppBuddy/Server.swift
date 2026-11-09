import Foundation

// Wire models for the SuppBuddy backend (backend/suppbuddy-backend/app/schemas.py).
// Property names match the JSON keys exactly so no key-conversion strategy can mangle them.

/// r,g,b,c: TCS34725 (transmitted light). scatter: TSL2591 full channel (light scattered at 90°). ir: its infrared channel.
struct Snapshot: Codable, Equatable {
    var r, g, b, c, scatter: Double
    var ir: Double? = nil
}

struct Sample: Codable, Equatable {
    var t_ms: Int
    var r, g, b, c, scatter: Double
    var ir: Double? = nil
    var led = "white" // white | r | g | b | off (a dark reading taken during the run)
}

struct DeviceReadings: Codable {
    var device_id: String
    var `protocol` = "v3"
    var led_mode = "cycle"
    var tcs_gain: Double?
    var tcs_integration_ms: Double?
    var tsl_gain: Double?
    var tsl_integration_ms: Double?
    var dark: Snapshot
    var blank: [String: Snapshot] // water blank per LED: "white", "r", "g", "b"
    var samples: [Sample]
}

/// How the sample was prepared. The server rescales color and cloudiness to its standard prep.
struct SamplePrep: Codable, Equatable {
    var mass_mg: Double?
    var volume_ml: Double?
    var stirred: Bool?
    var temp_c: Double?
}

/// Answer to "Yes, this is that product": added to the reference, or held because it doesn't match it.
struct ConfirmResult: Decodable {
    var n: Int
    var held: Bool?
    var reason: String?
}

struct LabelIngredient: Codable, Equatable {
    var name: String
    var amount: Double?
    var unit: String?
}

struct LabelInfo: Codable, Equatable {
    var brand: String?
    var product_name: String?
    var flavor: String? // part of the product's identity when there's no barcode
    var ingredients: [LabelIngredient] = []
    var other_ingredients: [String] = []
    var certifications: [String] = []
    var lot: String?
    var upc: String?
}

struct ScanReport: Codable {
    struct Accuracy: Codable { var label: String; var reference: String; var reference_n: Int; var reference_synthetic: Bool; var note: String; var max_z: Double? }
    struct Quality: Codable { var label: String; var issues: [String] }
    struct Finding: Codable { var text: String; var severity: String?; var url: String? }
    struct Reputability: Codable { var label: String; var score: Int?; var findings: [Finding] }
    struct Citation: Codable { var source: String; var title: String?; var url: String? }

    var verdict: String // CONSISTENT | CHECK | WARNING | NO_REF | BAD_SCAN
    var headline: String
    var summary: String
    var accuracy: Accuracy
    var quality: Quality
    var reputability: Reputability
    var key_findings: [String]
    var advice: [String]
    var citations: [Citation]
    var disclaimer: String
    var generated_by: String // deterministic | agent
}

struct Stage: Codable {
    var status: String?
    var reason: String?
    var error: String?
    var tainted: String?
    var recalls: String?
    var caers: String?
    var dsld: String?
}

struct QC: Codable {
    struct Series: Codable { var absorbance: [[Double]]; var scatter: [[Double]] } // [[seconds, value]]
    var ok: Bool
    var flags: [String]
    var warnings: [String]
    var series: Series?
}

struct Lcd: Codable { var code: String; var line1: String; var line2: String }

struct Scan: Codable {
    var id: String
    var status: String // pending | partial | complete | error
    var product_id: String?
    var confirmed: Bool
    var synthetic: Bool
    var label: LabelInfo?
    var qc: QC?
    var report: ScanReport?
    var stages: [String: Stage]?
    var lcd: Lcd
}

/// One line in the live progress feed.
struct Step: Codable, Equatable {
    let icon: String // SF Symbol name
    let text: String
}

/// Talks to the backend. The Claude key lives on the server; the app holds no secrets.
enum Server {
    static let defaultURL = "http://127.0.0.1:8000"
    static var base: String {
        let s = UserDefaults.standard.string(forKey: "server")?.trimmingCharacters(in: .whitespaces) ?? ""
        return s.isEmpty ? defaultURL : s
    }

    static func health() async throws -> [String: Any] {
        let (data, _) = try await send(request("/health"))
        return (try JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
    }

    static func extractLabel(jpeg: Data) async throws -> LabelInfo {
        let boundary = UUID().uuidString
        var body = Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"images\"; filename=\"label.jpg\"\r\n".utf8)
        body += Data("Content-Type: image/jpeg\r\n\r\n".utf8) + jpeg + Data("\r\n--\(boundary)--\r\n".utf8)
        var req = request("/label/extract", method: "POST", timeout: 90)
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "content-type")
        req.httpBody = body
        return try JSONDecoder().decode(LabelInfo.self, from: try await send(req).data)
    }

    static func createScan(label: LabelInfo?, readings: DeviceReadings, prep: SamplePrep?) async throws -> Scan {
        struct Body: Encodable { var label: LabelInfo?; var readings: DeviceReadings; var sample_prep: SamplePrep? }
        return try await post("/scans", Body(label: label, readings: readings, sample_prep: prep))
    }

    static func scan(_ id: String) async throws -> Scan {
        try JSONDecoder().decode(Scan.self, from: try await send(request("/scans/\(id)")).data)
    }

    /// Adds this scan to the crowd reference for its product, unless it's far from an established
    /// reference: then the server holds it for review and says why.
    static func confirm(_ id: String) async throws -> ConfirmResult {
        struct Empty: Encodable {}
        return try await post("/scans/\(id)/confirm", Empty())
    }

    /// Simulated device readings from the backend's simulator (used by the iOS Simulator's fake tester).
    static func devReadings(profile: String) async throws -> DeviceReadings {
        try JSONDecoder().decode(DeviceReadings.self, from: try await send(request("/dev/readings?profile=\(profile)&led_mode=cycle")).data)
    }

    private static func post<T: Decodable>(_ path: String, _ body: some Encodable) async throws -> T {
        var req = request(path, method: "POST")
        req.setValue("application/json", forHTTPHeaderField: "content-type")
        req.httpBody = try JSONEncoder().encode(body)
        return try JSONDecoder().decode(T.self, from: try await send(req).data)
    }

    private static func request(_ path: String, method: String = "GET", timeout: TimeInterval = 30) -> URLRequest {
        var req = URLRequest(url: URL(string: base + path) ?? URL(string: defaultURL + path)!, timeoutInterval: timeout)
        req.httpMethod = method
        return req
    }

    private static func send(_ req: URLRequest) async throws -> (data: Data, status: Int) {
        let data: Data, response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: req)
        } catch {
            throw AppError("Can't reach the SuppBuddy server at \(base). Is it running? (\(error.localizedDescription))")
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else { throw AppError(errorText(data, status: status)) }
        return (data, status)
    }

    /// FastAPI errors look like {"detail": "..."} (or a list of validation errors).
    static func errorText(_ data: Data, status: Int) -> String {
        let detail = ((try? JSONSerialization.jsonObject(with: data)) as? [String: Any])?["detail"]
        if let text = detail as? String { return text }
        return "Server error \(status): \(String(data: data, encoding: .utf8)?.prefix(200) ?? "")"
    }

    /// What the progress feed shows for the scan's current state.
    static func steps(for scan: Scan) -> [Step] {
        var out = [Step(icon: "paperplane", text: "Sent the readings and label to the server")]
        let stages = scan.stages ?? [:]
        switch stages["features"]?.status {
        case "ok": out.append(Step(icon: "waveform.path.ecg", text: "Measured color, cloudiness and dissolving speed"))
        case "qc_failed": out.append(Step(icon: "exclamationmark.triangle", text: "Scan check failed: " + (scan.qc?.flags ?? []).joined(separator: "; ")))
        case "error": out.append(Step(icon: "exclamationmark.triangle", text: "Couldn't process the readings"))
        default: break
        }
        switch stages["product"]?.status {
        case "ok":
            let name = [scan.label?.brand, scan.label?.product_name].compactMap { $0 }.joined(separator: " ")
            out.append(Step(icon: "shippingbox", text: "Product: \(name.isEmpty ? scan.product_id ?? "?" : name)"))
        case "unknown": out.append(Step(icon: "shippingbox", text: "No product name, so there's no reference to compare against"))
        default: break
        }
        if let d = stages["deterministic"] {
            let sources = [("FDA tainted list", d.tainted), ("FDA recalls", d.recalls), ("adverse events", d.caers), ("NIH labels", d.dsld)]
                .compactMap { name, status in status.map { "\(name) \($0.hasPrefix("ok") ? "checked" : $0.components(separatedBy: " (").first ?? $0)" } }
            out.append(Step(icon: "building.columns", text: sources.isEmpty ? "No label, so no public records to check" : "Public records: " + sources.joined(separator: ", ")))
            if let v = scan.report?.verdict {
                out.append(Step(icon: "checkmark.shield", text: "Verdict \(v), set by the measurements and records"))
            }
        }
        switch stages["agent"]?.status {
        case "ok": out.append(Step(icon: "sparkles", text: "Claude wrote the explanation"))
        case "skipped": out.append(Step(icon: "sparkles", text: "Explanation skipped (\(stages["agent"]?.reason ?? "no reason given"))"))
        case "unavailable": out.append(Step(icon: "sparkles", text: "Claude couldn't explain this one, so this is the measured report"))
        case nil where scan.status == "partial": out.append(Step(icon: "sparkles", text: "Claude is writing the explanation…"))
        default: break
        }
        if scan.status == "error" {
            out.append(Step(icon: "xmark.octagon", text: "Server error: \(stages["pipeline"]?.error ?? "unknown")"))
        }
        return out
    }
}
