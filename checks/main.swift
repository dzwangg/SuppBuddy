// Logic self-check, runs on the Mac without Xcode tests:
//   swiftc SupPal/Analysis.swift SupPal/Agent.swift SupPal/NIH.swift checks/main.swift -o /tmp/suppal-check && /tmp/suppal-check
import Foundation

func near(_ a: Double, _ b: Double) -> Bool { abs(a - b) < 1e-9 }

// BLE line framing: Arduino println sends "\r\n", chunks can split a line.
var buf = "100, 200,300\r\n4"
precondition(takeLines(&buf) == ["100, 200,300"] && buf == "4")
buf += "00,5\n\n"
precondition(takeLines(&buf) == ["400,5"] && buf.isEmpty)

precondition(parseReading("100, 200,300") == [100, 200, 300])
precondition(parseReading("abc,1") == nil)
precondition(parseReading("") == nil)

let a = absorbance(sample: [100, 10, 0], blank: [100, 100, 100])!
precondition(near(a[0], 0) && near(a[1], 1) && near(a[2], 2)) // zero clamps to 1 count
precondition(absorbance(sample: [1], blank: [1, 2]) == nil)

precondition(near(similarity([1, 2], [2, 4]), 1))
precondition(similarity([0, 0], [1, 1]) == 0)
precondition(similarity([1], [1, 2]) == 0)

// Bundled reference DB parses, and the simulator's mock sample matches riboflavin.
let refs = try JSONDecoder().decode([Reference].self, from: Data(contentsOf: URL(fileURLWithPath: "SupPal/references.json")))
precondition(refs.count == 5 && refs.allSatisfy { $0.absorbance.count == 8 })
let mock = [0.61, 0.93, 0.72, 0.19, 0.05, 0.03, 0.02, 0.02]
precondition(topMatches(mock, in: refs).first?.reference.product == "Riboflavin (B2) (demo)")

// Report comes out of the submit_report tool call, skipping thinking / search blocks.
let content: [[String: Any]] = [
    ["type": "thinking", "thinking": "", "signature": "x"],
    ["type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": ["query": "brand"]],
    ["type": "tool_use", "id": "toolu_1", "name": "submit_report", "input": [
        "product": "B2 100 mg", "brand": "Acme", "verdict": "consistent", "spectrum_match": "fits",
        "reputation": "no recalls", "summary": "ok", "concerns": [String](),
        "sources": [["title": "FDA", "url": "https://fda.gov"]],
    ]],
]
let report = try Agent.report(in: content)!
precondition(report.brand == "Acme" && report.spectrumMatch == "fits" && report.sources.first?.url == "https://fda.gov")
let none = try Agent.report(in: [["type": "text", "text": "hi"]])
precondition(none == nil)

// Streamed events rebuild the message (for pause_turn and the report) and produce feed steps.
let reportJSON = #"{"brand":"Acme","concerns":[],"product":"B2","reputation":"ok","sources":[],"spectrum_match":"fits","summary":"Fine.","verdict":"consistent"}"#
let events: [[String: Any]] = [
    ["type": "message_start", "message": [:]],
    ["type": "content_block_start", "index": 0, "content_block": ["type": "thinking", "thinking": "", "signature": ""]],
    ["type": "content_block_delta", "index": 0, "delta": ["type": "thinking_delta", "thinking": "Checking the FDA record."]],
    ["type": "content_block_delta", "index": 0, "delta": ["type": "signature_delta", "signature": "sig"]],
    ["type": "content_block_stop", "index": 0],
    ["type": "content_block_start", "index": 1, "content_block": ["type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": [:]]],
    ["type": "content_block_delta", "index": 1, "delta": ["type": "input_json_delta", "partial_json": #"{"query": "Acme"#]],
    ["type": "content_block_delta", "index": 1, "delta": ["type": "input_json_delta", "partial_json": #" recall"}"#]],
    ["type": "content_block_stop", "index": 1],
    ["type": "content_block_start", "index": 2, "content_block": ["type": "web_search_tool_result", "tool_use_id": "srvtoolu_1", "content": [
        ["type": "web_search_result", "url": "https://www.fda.gov/a", "title": "FDA"],
        ["type": "web_search_result", "url": "https://nsf.org/b", "title": "NSF"],
        ["type": "web_search_result", "url": "https://fda.gov/c", "title": "FDA 2"],
    ]]],
    ["type": "content_block_stop", "index": 2],
    ["type": "content_block_start", "index": 3, "content_block": ["type": "text", "text": "", "citations": []]],
    ["type": "content_block_delta", "index": 3, "delta": ["type": "citations_delta", "citation": ["type": "web_search_result_location", "url": "https://fda.gov/a"]]],
    ["type": "content_block_delta", "index": 3, "delta": ["type": "text_delta", "text": "no recalls"]],
    ["type": "content_block_stop", "index": 3],
    ["type": "content_block_start", "index": 4, "content_block": ["type": "tool_use", "id": "toolu_1", "name": "submit_report", "input": [:]]],
    ["type": "content_block_delta", "index": 4, "delta": ["type": "input_json_delta", "partial_json": String(reportJSON.prefix(40))]],
    ["type": "content_block_delta", "index": 4, "delta": ["type": "input_json_delta", "partial_json": String(reportJSON.dropFirst(40))]],
    ["type": "content_block_stop", "index": 4],
    ["type": "message_delta", "delta": ["stop_reason": "tool_use"]],
    ["type": "message_stop"],
]
var stream = MessageStream()
let feed = try events.compactMap { try stream.apply($0) }.map(\.text)
precondition(feed == ["Checking the FDA record.", "Searching “Acme recall”", "Read fda.gov, nsf.org", "Writing the report…"], "\(feed)")
precondition(stream.stopReason == "tool_use")
precondition(stream.content[0]["signature"] as? String == "sig") // echoed back unchanged on pause_turn
precondition((stream.content[3]["citations"] as? [Any])?.count == 1)
let streamed = try Agent.report(in: stream.content)
precondition(streamed?.summary == "Fine.")
var failed = MessageStream()
do { _ = try failed.apply(["type": "error", "error": ["type": "overloaded_error", "message": "Overloaded"]]); preconditionFailure("should throw") }
catch { precondition(error.localizedDescription == "Overloaded") }

// History survives a save/load round trip; an unreadable file is set aside, not overwritten.
let dir = FileManager.default.temporaryDirectory.appending(path: "suppal-check-\(UUID())")
try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
let file = dir.appending(path: "history.json")
let saved = TestRecord(date: Date(timeIntervalSince1970: 0), report: report, spectrum: mock, match: topMatches(mock, in: refs).first,
                       steps: [Step(icon: "sparkles", text: "hi")], thumbnail: Data([1, 2, 3]))
History.save([saved], to: file)
let loaded = History.load(from: file)
precondition(loaded.count == 1 && loaded[0].id == saved.id && loaded[0].report.spectrumMatch == "fits")
precondition(loaded[0].match?.reference.product == "Riboflavin (B2) (demo)" && loaded[0].steps == saved.steps && loaded[0].thumbnail == Data([1, 2, 3]))
try Data("not json".utf8).write(to: file)
precondition(History.load(from: file).isEmpty && FileManager.default.fileExists(atPath: file.appendingPathExtension("bak").path))
// A test saved before labelCheck/official existed still loads.
let oldJSON = #"[{"id":"\#(UUID().uuidString)","date":0,"spectrum":[0.5],"steps":[],"thumbnail":"AQID","report":{"brand":"A","concerns":[],"product":"P","reputation":"r","sources":[],"spectrumMatch":"s","summary":"x","verdict":"consistent"}}]"#
try Data(oldJSON.utf8).write(to: file)
let old = History.load(from: file)
precondition(old.count == 1 && old[0].report.labelCheck == nil && old[0].official == nil)
try? FileManager.default.removeItem(at: dir)

// Barcodes: scanners give EAN-13 with a leading 0 for UPC-A; typos fail the check digit.
precondition(NIH.dsldFormat("0700580723633") == "7 00580 72363 3")
precondition(NIH.dsldFormat("7 00580 72363 3") == "7 00580 72363 3")
precondition(NIH.dsldFormat("700580723634") == nil) // wrong check digit
precondition(NIH.dsldFormat("000000000000") == nil) // placeholder in some database entries
precondition(NIH.dsldFormat("12345") == nil)

// NIH label record (trimmed from api.ods.od.nih.gov/dsld/v9/label/211102).
let nihRecord: [String: Any] = [
    "id": 211102, "brandName": "Seeking Health", "fullName": "Riboflavin 400 mg", "upcSku": "7 00580 72363 3", "offMarket": 0,
    "ingredientRows": [["name": "Riboflavin", "quantity": [["quantity": 400, "unit": "mg"]]], ["name": "Proprietary Blend"]],
    "otheringredients": ["text": NSNull(), "ingredients": [["name": "HPMC"], ["name": "Silica"]]],
]
let official = NIH.parse(nihRecord)!
precondition(official.brand == "Seeking Health" && official.onMarket && official.upc == "7 00580 72363 3")
precondition(official.ingredients == ["Riboflavin 400 mg", "Proprietary Blend"] && official.otherIngredients == ["HPMC", "Silica"])
precondition(official.url == "https://dsld.od.nih.gov/label/211102")
precondition(NIH.parse(["id": 1]) == nil) // no barcode on the record

// The prompt tells Claude what the barcode lookup found.
precondition(Agent.prompt(spectrum: mock, matches: [], barcode: "0700580723633", official: official).contains("Riboflavin 400 mg"))
precondition(Agent.prompt(spectrum: mock, matches: [], barcode: "036000291452", official: nil).contains("not in the NIH"))
precondition(Agent.prompt(spectrum: mock, matches: [], barcode: nil, official: nil).contains("No barcode was scanned"))

print("all checks passed")
