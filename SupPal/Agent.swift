import Foundation

struct Report: Codable {
    struct Source: Codable { let title: String; let url: String }
    let product: String
    let brand: String
    let verdict: String // consistent | questionable | concerning | inconclusive
    let spectrumMatch: String
    let labelCheck: String? // optional so reports saved before this field existed still load
    let reputation: String
    let summary: String
    let concerns: [String]
    let sources: [Source]
}

/// One line in the live research feed.
struct Step: Codable, Equatable {
    let icon: String // SF Symbol name
    let text: String
}

/// Sends label photo + spectrum + DB matches to Claude (with web search) and gets a Report back,
/// streaming each research step to `onStep` as it happens.
enum Agent {
    // ponytail: key ships inside the app binary, fine for a hackathon demo.
    // Before TestFlight/App Store, move this call behind your own server.
    static var apiKey: String { Bundle.main.object(forInfoDictionaryKey: "AnthropicAPIKey") as? String ?? "" }

    static func analyze(labelJPEG: Data, spectrum: [Double], matches: [Match], barcode: String?, official: OfficialLabel?,
                        onStep: @escaping @MainActor (Step) -> Void) async throws -> Report {
        let key = apiKey
        guard !key.isEmpty else { throw AppError("No API key. Copy Secrets.example.xcconfig to Secrets.xcconfig, add your key, rebuild.") }

        var messages: [[String: Any]] = [["role": "user", "content": [
            ["type": "image", "source": ["type": "base64", "media_type": "image/jpeg", "data": labelJPEG.base64EncodedString()]],
            ["type": "text", "text": prompt(spectrum: spectrum, matches: matches, barcode: barcode, official: official)],
        ]]]

        for _ in 0..<6 {
            let (content, stop) = try await stream(messages, key: key, onStep: onStep)
            if let report = try report(in: content) { return report }

            switch stop {
            case "pause_turn": // server paused its web-search loop; send the partial turn back and it resumes
                messages.append(["role": "assistant", "content": content])
            case "end_turn": // answered in prose instead of calling the tool
                messages.append(["role": "assistant", "content": content])
                messages.append(["role": "user", "content": "Call submit_report with your findings now."])
            case "refusal":
                throw AppError("Claude declined to analyze this request.")
            default:
                throw AppError("Analysis stopped early (\(stop)).")
            }
        }
        throw AppError("Analysis took too many steps. Try again.")
    }

    /// The report is the input of the submit_report tool call, if Claude made one.
    static func report(in content: [[String: Any]]) throws -> Report? {
        guard let input = content.first(where: { $0["type"] as? String == "tool_use" && $0["name"] as? String == "submit_report" })?["input"]
        else { return nil }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Report.self, from: JSONSerialization.data(withJSONObject: input))
    }

    /// What to show in the feed for a finished content block, if anything.
    static func step(for block: [String: Any]) -> Step? {
        switch block["type"] as? String {
        case "thinking", "text":
            // Under display "updates", non-empty thinking blocks are Claude's progress notes; reasoning stays empty.
            // Cited text arrives in sentence fragments, so it's left out of the feed.
            if (block["citations"] as? [Any])?.isEmpty == false { return nil }
            let text = (block["thinking"] as? String ?? block["text"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return text.isEmpty ? nil : Step(icon: "sparkles", text: text)
        case "server_tool_use":
            guard block["name"] as? String == "web_search",
                  let query = (block["input"] as? [String: Any])?["query"] as? String else { return nil }
            return Step(icon: "magnifyingglass", text: "Searching “\(query.replacingOccurrences(of: "\"", with: ""))”")
        case "web_search_tool_result":
            guard let results = block["content"] as? [[String: Any]] else { return nil } // errors come as an object, not a list
            var hosts: [String] = []
            for r in results {
                if let host = URL(string: r["url"] as? String ?? "")?.host?.replacingOccurrences(of: "www.", with: ""),
                   !hosts.contains(host) { hosts.append(host) }
            }
            if hosts.isEmpty { return Step(icon: "doc.text.magnifyingglass", text: "No results") }
            let more = hosts.count > 3 ? " +\(hosts.count - 3) more" : ""
            return Step(icon: "doc.text.magnifyingglass", text: "Read \(hosts.prefix(3).joined(separator: ", "))\(more)")
        default:
            return nil
        }
    }

    static func prompt(spectrum: [Double], matches: [Match], barcode: String?, official: OfficialLabel?) -> String {
        let a = spectrum.map { String(format: "%.3f", $0) }.joined(separator: ", ")
        let m = matches.map { "- \($0.reference.product): \(String(format: "%.3f", $0.similarity))" }.joined(separator: "\n")
        let nih: String
        switch (barcode, official) {
        case (_, let o?):
            nih = """
            Official label registered for this barcode (UPC \(o.upc)) in the NIH Dietary Supplement Label Database:
            Brand: \(o.brand). Product: \(o.product). Status: \(o.onMarket ? "on the market" : "listed as discontinued").
            Active ingredients per serving: \(o.ingredients.joined(separator: "; ")).
            Other ingredients: \(o.otherIngredients.isEmpty ? "none listed" : o.otherIngredients.joined(separator: ", ")).
            Record: \(o.url)
            """
        case (let code?, nil):
            nih = "The bottle's barcode (\(code)) is not in the NIH Dietary Supplement Label Database. Many products aren't; that alone is not a red flag."
        default:
            nih = "No barcode was scanned, so there is no official label to compare against."
        }
        return """
        The attached photo is the supplement's label.
        Measured absorbance per sensor channel (\(spectrum.count) channels, short to long wavelength): \(a)
        Closest crowdsourced reference spectra (cosine similarity, 1.000 = identical shape):
        \(m.isEmpty ? "(no references available)" : m)

        \(nih)
        """
    }

    static let system = """
    You help consumers sanity-check dietary supplements, which are lightly regulated in the US.
    You get a photo of the label, an absorbance spectrum the user measured with a low-cost home cuvette \
    tester (a few visible-light channels), and the closest matches from a crowdsourced reference database.

    1. Read the label: brand, product, claimed active ingredients and doses.
    2. Judge whether the closest reference matches what the label claims. This tester is low resolution: \
    it can flag a sample that looks wrong, but it cannot confirm identity, dose, or purity. Say which.
    3. If an official NIH label is provided, compare it with the photographed label: brand, product name, \
    ingredients and doses. A mismatch can mean relabeling, a counterfeit, or a reformulation; a discontinued \
    listing on a bottle sold today is worth noting.
    4. Search the web for the brand and product: FDA warning letters, recalls, third-party certification \
    (USP, NSF, Informed Choice), and independent lab testing.
    5. Call submit_report once. Be factual, cite the pages you used, and give no medical advice.

    The user watches your progress live: before each search, say in one short sentence what you are checking and why.
    """

    static let tools: [[String: Any]] = [
        ["type": "web_search_20260209", "name": "web_search", "max_uses": 8], // 5 ran out before certification checks
        [
            "name": "submit_report",
            "description": "Submit the final report shown to the user. Call exactly once, after your research.",
            "strict": true,
            "input_schema": [
                "type": "object",
                "additionalProperties": false,
                // Keys are sent sorted (see stream), so Claude fills these alphabetically: evidence first, summary and verdict last.
                "required": ["brand", "concerns", "label_check", "product", "reputation", "sources", "spectrum_match", "summary", "verdict"],
                "properties": [
                    "product": ["type": "string", "description": "Product name and claimed active ingredients/doses from the label"],
                    "brand": ["type": "string"],
                    "verdict": [
                        "type": "string",
                        "enum": ["consistent", "questionable", "concerning", "inconclusive"],
                        "description": "consistent: spectrum fits the label and no red flags found. questionable: weak spectrum fit or a thin/unknown brand track record. concerning: spectrum contradicts the label, or recalls/warning letters/failed lab tests. inconclusive: not enough data to judge.",
                    ],
                    "spectrum_match": ["type": "string", "description": "Whether the measured spectrum fits this product, and what this test cannot show"],
                    "label_check": ["type": "string", "description": "How the photographed label compares with the official NIH label for its barcode, or why no comparison was possible"],
                    "reputation": ["type": "string", "description": "Recalls, FDA warning letters, certifications, independent lab results"],
                    "summary": ["type": "string", "description": "The bottom line for the user in two or three plain sentences, drawn from all the findings above. Never a placeholder."],
                    "concerns": ["type": "array", "items": ["type": "string"]],
                    "sources": ["type": "array", "items": [
                        "type": "object",
                        "additionalProperties": false,
                        "required": ["title", "url"],
                        "properties": ["title": ["type": "string"], "url": ["type": "string"]],
                    ]],
                ],
            ],
        ],
    ]

    // ponytail: no automatic retry on 429/529; the user can tap Analyze again.
    static func stream(_ messages: [[String: Any]], key: String, onStep: @MainActor (Step) -> Void) async throws -> (content: [[String: Any]], stop: String) {
        var request = URLRequest(url: URL(string: "https://api.anthropic.com/v1/messages")!, timeoutInterval: 300)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "content-type")
        request.setValue(key, forHTTPHeaderField: "x-api-key")
        request.setValue("2026-10-21", forHTTPHeaderField: "anthropic-version")
        request.setValue("server-side-fallback-2026-07-01,thinking-display-updates-2026-08-18", forHTTPHeaderField: "anthropic-beta")
        let body: [String: Any] = [
            "model": "claude-opus-5-5",
            "max_tokens": 64000,
            "stream": true,
            "thinking": ["type": "adaptive", "display": "updates"], // Claude's between-search notes come back as text
            "output_config": ["effort": "medium"],
            "fallbacks": "default", // if a safety classifier declines, the API retries on a fallback model
            "system": system,
            "tools": tools,
            "messages": messages,
        ]
        // Sorted keys: Swift dictionaries have no order, so without this the schema field order changes every
        // request (Claude once wrote the summary first and left "placeholder"), and prompt caching never hits.
        request.httpBody = try JSONSerialization.data(withJSONObject: body, options: [.sortedKeys])

        let (bytes, response) = try await URLSession.shared.bytes(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard status == 200 else {
            var data = Data()
            for try await byte in bytes { data.append(byte) }
            let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            throw AppError(((json?["error"] as? [String: Any])?["message"] as? String) ?? "Claude API returned HTTP \(status).")
        }

        var message = MessageStream()
        for try await line in bytes.lines where line.hasPrefix("data:") {
            guard let event = (try? JSONSerialization.jsonObject(with: Data(line.dropFirst(5).utf8))) as? [String: Any] else { continue }
            if let step = try message.apply(event) { await onStep(step) }
        }
        return (message.content, message.stopReason ?? "unknown")
    }
}

/// Rebuilds the assistant message from streamed events. The full content is needed to resume a paused
/// web-search turn (it must be sent back unchanged, signatures included) and to read the report.
// ponytail: doesn't trim blocks before a mid-output safety fallback; a pause_turn right after one would be rejected.
struct MessageStream {
    var content: [[String: Any]] = []
    var stopReason: String?
    private var partialJSON: [Int: String] = [:]

    /// Applies one event; returns a feed step if this event finished something worth showing.
    mutating func apply(_ event: [String: Any]) throws -> Step? {
        let i = event["index"] as? Int ?? -1
        switch event["type"] as? String {
        case "content_block_start":
            guard let block = event["content_block"] as? [String: Any] else { return nil }
            content.append(block)
            return block["type"] as? String == "tool_use" ? Step(icon: "square.and.pencil", text: "Writing the report…") : nil
        case "content_block_delta" where content.indices.contains(i):
            let delta = event["delta"] as? [String: Any] ?? [:]
            switch delta["type"] as? String {
            case "text_delta": append(delta["text"], to: "text", at: i)
            case "thinking_delta": append(delta["thinking"], to: "thinking", at: i)
            case "signature_delta": append(delta["signature"], to: "signature", at: i)
            case "input_json_delta": partialJSON[i, default: ""] += delta["partial_json"] as? String ?? ""
            case "citations_delta":
                if let c = delta["citation"] { content[i]["citations"] = (content[i]["citations"] as? [Any] ?? []) + [c] }
            default: break
            }
        case "content_block_stop" where content.indices.contains(i):
            if let json = partialJSON.removeValue(forKey: i), !json.isEmpty {
                content[i]["input"] = try JSONSerialization.jsonObject(with: Data(json.utf8))
            }
            return Agent.step(for: content[i])
        case "message_delta":
            stopReason = (event["delta"] as? [String: Any])?["stop_reason"] as? String ?? stopReason
        case "error":
            throw AppError(((event["error"] as? [String: Any])?["message"] as? String) ?? "Claude stream failed.")
        default:
            break
        }
        return nil
    }

    private mutating func append(_ piece: Any?, to key: String, at i: Int) {
        content[i][key] = (content[i][key] as? String ?? "") + (piece as? String ?? "")
    }
}
