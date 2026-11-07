import Foundation

/// The official label registered for a barcode in the NIH Dietary Supplement Label Database (dsld.od.nih.gov).
struct OfficialLabel: Codable, Equatable {
    let id: Int
    let brand: String
    let product: String
    let upc: String
    let onMarket: Bool
    let ingredients: [String] // "Riboflavin 400 mg"
    let otherIngredients: [String]

    var url: String { "https://dsld.od.nih.gov/label/\(id)" }
}

enum NIH {
    /// Scanners report UPC-A as 12 digits, or as EAN-13 with a leading 0. The database stores "7 00580 72363 3".
    // ponytail: UPC-A only (what US supplements use); add UPC-E/EAN-13 if non-US bottles matter.
    static func dsldFormat(_ code: String) -> String? {
        var d = Array(code.filter(\.isNumber))
        if d.count == 13, d.first == "0" { d.removeFirst() }
        guard d.count == 12 else { return nil }
        // Check digit catches typos; all zeros is a placeholder some database entries use.
        let n: [Int] = d.compactMap(\.wholeNumberValue)
        var sum = 0
        for i in 0..<11 { sum += i % 2 == 0 ? 3 * n[i] : n[i] }
        guard (10 - sum % 10) % 10 == n[11], n.contains(where: { $0 != 0 }) else { return nil }
        return "\(d[0]) \(String(d[1...5])) \(String(d[6...10])) \(d[11])"
    }

    /// nil when the barcode isn't in the database, which is common and not by itself a red flag.
    static func lookup(barcode: String) async throws -> OfficialLabel? {
        guard let upc = dsldFormat(barcode) else { throw AppError("\(barcode) isn't a valid UPC barcode. Check the digits.") }
        var search = URLComponents(string: "https://api.ods.od.nih.gov/dsld/v9/search-filter")!
        search.queryItems = [URLQueryItem(name: "q", value: "\"\(upc)\""), URLQueryItem(name: "size", value: "10")]
        let hits = try await json(search.url!)["hits"] as? [[String: Any]] ?? []

        // Several label versions can share a barcode: on-market first, then newest.
        let ranked = hits.compactMap { hit -> (id: String, off: Int, date: String)? in
            guard let id = hit["_id"] as? String, let s = hit["_source"] as? [String: Any] else { return nil }
            return (id, s["offMarket"] as? Int ?? 1, s["entryDate"] as? String ?? "")
        }
        .sorted { ($0.off, $1.date) < ($1.off, $0.date) }

        // Search is full-text, so confirm the barcode on the full record.
        for hit in ranked.prefix(3) {
            if let label = parse(try await json(URL(string: "https://api.ods.od.nih.gov/dsld/v9/label/\(hit.id)")!)), label.upc == upc {
                return label
            }
        }
        return nil
    }

    static func parse(_ s: [String: Any]) -> OfficialLabel? {
        guard let id = s["id"] as? Int, let upc = s["upcSku"] as? String else { return nil }
        let ingredients = (s["ingredientRows"] as? [[String: Any]] ?? []).compactMap { row -> String? in
            guard let name = row["name"] as? String else { return nil }
            guard let q = (row["quantity"] as? [[String: Any]])?.first,
                  let amount = (q["quantity"] as? NSNumber)?.doubleValue, let unit = q["unit"] as? String else { return name }
            return "\(name) \(amount.formatted()) \(unit)"
        }
        let other = ((s["otheringredients"] as? [String: Any])?["ingredients"] as? [[String: Any]] ?? [])
            .compactMap { $0["name"] as? String }
        return OfficialLabel(id: id, brand: s["brandName"] as? String ?? "", product: s["fullName"] as? String ?? "",
                             upc: upc, onMarket: s["offMarket"] as? Int == 0, ingredients: ingredients, otherIngredients: other)
    }

    private static func json(_ url: URL) async throws -> [String: Any] {
        let (data, response) = try await URLSession.shared.data(from: url)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw AppError("The NIH label database didn't respond. Try again.") }
        return (try JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
    }
}
