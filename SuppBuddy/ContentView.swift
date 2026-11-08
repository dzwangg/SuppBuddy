import Charts
import SwiftUI
import Vision
import VisionKit

struct ContentView: View {
    @State private var device = Device()
    @State private var blank: BlankSet?
    @State private var samples: [Sample] = []
    // The locked sample prep; the server rescales scans made with a different amount.
    @AppStorage("sampleMassMg") private var sampleMassMg = 500.0
    @AppStorage("sampleVolumeMl") private var sampleVolumeMl = 50.0
    @State private var photo: UIImage?
    @State private var label = LabelInfo()
    @State private var labelNote: String?
    @State private var readingLabel = false
    @State private var official: OfficialLabel?
    @State private var barcodeNote: String?
    @State private var lookingUp = false
    @State private var showPicker = false
    @State private var showScanner = false
    @State private var typingBarcode = false
    @State private var typedCode = ""
    @State private var busy: String?
    @State private var error: String?
    @State private var steps: [Step] = []
    @State private var current: TestRecord?
    @State private var showReport = false
    @State private var showSettings = false
    @State private var history = History.load()

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(spacing: 16) {
                        statusPill

                        StepCard(number: 1, title: "Water blank",
                                 detail: "Fill the cuvette with clean water, insert it, then measure. This also takes a dark reading with the light off.",
                                 done: blank != nil) {
                            Button(blank == nil ? "Measure blank" : "Re-measure blank") {
                                run("Measuring blank…") { blank = try await device.measureBlank(); samples = []; steps = [] }
                            }
                            .buttonStyle(.bordered)
                            .disabled(!device.isReady)
                        }

                        StepCard(number: 2, title: "Sample",
                                 detail: "Stir \(Int(sampleMassMg)) mg of the supplement into \(Int(sampleVolumeMl)) mL of water, fill the cuvette, insert it, then start. Keep it still for the whole run (30 seconds).",
                                 done: whiteSamples.count >= 10 && busy == nil) {
                            Button(samples.isEmpty ? "Start run" : "Run again") {
                                samples = []
                                steps = []
                                run("Reading the sample…") { _ = try await device.runSample { samples.append($0) } }
                            }
                            .buttonStyle(.bordered)
                            .disabled(blank == nil || !device.isReady)
                            if !whiteSamples.isEmpty, let blank, let white = blank.white {
                                let points = whiteSamples.compactMap { livePoint($0, dark: blank.dark, blank: white) }
                                DissolutionChart(absorbance: points.map { [$0.seconds, $0.absorbance] },
                                                 cloudiness: points.map { [$0.seconds, $0.cloudiness] })
                            }
                        }

                        StepCard(number: 3, title: "Product",
                                 detail: "Photograph the label and scan its barcode. No label? Type what it was sold as.",
                                 done: label.product_name != nil) {
                            HStack {
                                Button(photo == nil ? "Photograph label" : "Retake", systemImage: "camera") { showPicker = true }
                                Button("Barcode", systemImage: "barcode.viewfinder") { scanBarcode() }
                            }
                            .buttonStyle(.bordered)
                            .disabled(readingLabel || lookingUp)
                            if let photo {
                                Color.clear.frame(height: 140)
                                    .overlay { Image(uiImage: photo).resizable().scaledToFill() }
                                    .clipShape(RoundedRectangle(cornerRadius: 12))
                            }
                            if readingLabel { ProgressView("Reading the label…").font(.subheadline) }
                            if lookingUp { ProgressView("Checking the NIH label database…").font(.subheadline) }
                            if let labelNote { Text(labelNote).font(.subheadline).foregroundStyle(.secondary) }
                            Group { // brand names aren't dictionary words; autocorrect turned "DemoLabs" into "Demo labs"
                                TextField("Brand", text: field(\.brand))
                                TextField("Product (or what it was sold as)", text: field(\.product_name))
                                TextField("Flavor (if any)", text: field(\.flavor))
                            }
                            .textFieldStyle(.roundedBorder)
                            .autocorrectionDisabled()
                            if let official { OfficialLabelCard(label: official) }
                            if let barcodeNote { Text(barcodeNote).font(.subheadline).foregroundStyle(.secondary) }
                        }

                        analyzeSection

                        Text("SuppBuddy is a screening tool, not a certified lab test or medical advice.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                            .id("bottom")
                    }
                    .padding()
                    .disabled(busy != nil)
                }
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: steps.count) { withAnimation { proxy.scrollTo("bottom", anchor: .bottom) } }
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("SuppBuddy")
            .toolbar {
                ToolbarItemGroup(placement: .primaryAction) {
                    NavigationLink { HistoryView(records: $history, confirm: confirm) } label: {
                        Label("History", systemImage: "clock.arrow.circlepath")
                    }
                    Button("Settings", systemImage: "gearshape") { showSettings = true }
                }
            }
            .sheet(isPresented: $showPicker) { ImagePicker(image: $photo).ignoresSafeArea() }
            .sheet(isPresented: $showSettings) { SettingsView() }
            .sheet(isPresented: $showScanner) {
                BarcodeScanner { code in
                    showScanner = false
                    lookUp(code)
                }
                .ignoresSafeArea()
            }
            .sheet(isPresented: $showReport) {
                if let current {
                    NavigationStack {
                        ReportView(record: current, confirm: confirm)
                            .toolbar {
                                ToolbarItem(placement: .cancellationAction) { Button("Done") { showReport = false } }
                            }
                    }
                }
            }
            .alert("Enter the barcode number", isPresented: $typingBarcode) {
                TextField("12-digit UPC", text: $typedCode).keyboardType(.numberPad)
                Button("Look up") { lookUp(typedCode) }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("The camera scanner isn't available here, so type the digits printed under the barcode.")
            }
            .onChange(of: photo) { readLabel() }
        }
    }

    private var statusPill: some View {
        HStack(spacing: 8) {
            Circle().fill(device.isReady ? Color.green : Color.orange).frame(width: 8, height: 8)
            Text(device.status).font(.subheadline)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Color(.secondarySystemGroupedBackground), in: Capsule())
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var analyzeSection: some View {
        VStack(spacing: 12) {
            Button(action: analyze) {
                Label("Analyze", systemImage: "sparkles").font(.headline).frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(blank == nil || whiteSamples.count < 10 || readingLabel || lookingUp)

            if let busy, steps.isEmpty { ProgressView(busy).font(.subheadline) }
            if !steps.isEmpty { ResearchFeed(steps: steps, live: busy != nil) }
            if let error { Text(error).font(.subheadline).foregroundStyle(.red) }
            if current != nil, busy == nil {
                Button("View last report") { showReport = true }
            }
        }
    }

    /// White-light readings drive the live chart (the colored-LED and dark readings go to the server).
    private var whiteSamples: [Sample] { samples.filter { $0.led == "white" } }

    private func field(_ key: WritableKeyPath<LabelInfo, String?>) -> Binding<String> {
        Binding(get: { label[keyPath: key] ?? "" }, set: { label[keyPath: key] = $0.isEmpty ? nil : $0 })
    }

    /// Sends the readings and label, then follows the server's stages until Claude's explanation lands.
    private func analyze() {
        guard let blank else { return }
        let readings = makeReadings(deviceID: device.id, blank: blank, samples: samples)
        let prep = SamplePrep(mass_mg: sampleMassMg, volume_ml: sampleVolumeMl, stirred: true)
        let sent = label == LabelInfo() ? nil : label
        let thumbnail = photo.map { jpeg($0, maxSide: 240) }
        steps = [Step(icon: "paperplane", text: "Sending the readings to the server")]
        run("Analyzing…") {
            var scan = try await Server.createScan(label: sent, readings: readings, prep: prep)
            var record: TestRecord?
            let started = Date.now
            var onScreen: Lcd?
            var failedPolls = 0
            while true {
                withAnimation { steps = Server.steps(for: scan) }
                if scan.lcd != onScreen { // tester screen: "Analyzing..." now, the verdict as soon as it's set
                    device.show(scan.lcd)
                    onScreen = scan.lcd
                }
                if scan.report != nil { // the measured verdict arrives in seconds; Claude's explanation follows
                    record = TestRecord(id: record?.id ?? UUID(), date: record?.date ?? .now, scan: scan, steps: steps, thumbnail: thumbnail)
                    if current?.id != record?.id { showReport = true }
                    current = record
                }
                // The server gives the explanation up to 90 s; stop following a little after that.
                if scan.status == "complete" || scan.status == "error" || Date.now.timeIntervalSince(started) > 120 { break }
                try await Task.sleep(for: .seconds(1))
                do {
                    scan = try await Server.scan(scan.id)
                    failedPolls = 0
                } catch { // flaky Wi-Fi: keep the verdict already on screen instead of dropping the whole test
                    failedPolls += 1
                    if failedPolls >= 3 { if record != nil { break } else { throw error } }
                }
            }
            guard let record else { throw AppError("The server couldn't finish this scan. Try again.") }
            history.insert(record, at: 0)
            History.save(history)
        }
    }

    private func confirm(_ record: TestRecord) async throws -> ConfirmResult {
        let result = try await Server.confirm(record.scan.id)
        guard result.held != true else { return result } // not added; nothing to mark
        if let i = history.firstIndex(where: { $0.id == record.id }) {
            history[i].scan.confirmed = true
            History.save(history)
        }
        if current?.id == record.id { current?.scan.confirmed = true }
        return result
    }

    private func readLabel() {
        guard let photo else { return }
        readingLabel = true
        labelNote = nil
        Task {
            do {
                var read = try await Server.extractLabel(jpeg: jpeg(photo, maxSide: 1568))
                read.upc = read.upc ?? label.upc // keep a barcode that was already scanned
                label = read
                labelNote = "Read from the photo. Check the brand and product below."
            } catch {
                labelNote = "Couldn't read the label automatically: \(error.localizedDescription) Type the brand and product below."
            }
            readingLabel = false
        }
    }

    /// Live scanner on a real iPhone; typed digits where there's no camera (Simulator) or camera access was denied.
    private func scanBarcode() {
        if DataScannerViewController.isSupported && DataScannerViewController.isAvailable {
            showScanner = true
        } else {
            typedCode = ""
            typingBarcode = true
        }
    }

    private func lookUp(_ code: String) {
        official = nil
        barcodeNote = nil
        lookingUp = true
        Task {
            do {
                official = try await NIH.lookup(barcode: code)
                label.upc = code // the server checks it against the label too
                if let o = official {
                    if label.brand == nil { label.brand = o.brand }
                    if label.product_name == nil { label.product_name = o.product }
                } else {
                    barcodeNote = "Barcode \(code) isn't in the NIH label database. Many products aren't."
                }
            } catch {
                barcodeNote = error.localizedDescription
            }
            lookingUp = false
        }
    }

    private func run(_ message: String, _ work: @escaping () async throws -> Void) {
        busy = message
        error = nil
        Task {
            do { try await work() } catch { self.error = error.localizedDescription }
            busy = nil
        }
    }

    /// Claude reads images best at <=1568 px on the long edge; the history thumbnail uses a much smaller size.
    private func jpeg(_ image: UIImage, maxSide: CGFloat) -> Data {
        let scale = min(1, maxSide / max(image.size.width, image.size.height))
        let size = CGSize(width: image.size.width * scale, height: image.size.height * scale)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        return UIGraphicsImageRenderer(size: size, format: format).jpegData(withCompressionQuality: 0.8) { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
    }
}

struct StepCard<Content: View>: View {
    let number: Int
    let title: String
    let detail: String
    let done: Bool
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: done ? "checkmark.circle.fill" : "\(number).circle")
                    .font(.title2)
                    .foregroundStyle(done ? Color.green : Color.secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.headline)
                    Text(detail).font(.subheadline).foregroundStyle(.secondary)
                }
            }
            content
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
    }
}

/// How the sample changes while it dissolves: color absorbance and cloudiness over time. [[seconds, value]].
struct DissolutionChart: View {
    let absorbance: [[Double]]
    let cloudiness: [[Double]]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Color absorbance").font(.caption).foregroundStyle(.secondary)
            chart(absorbance, color: .indigo)
            Text("Cloudiness (1 = as clear as water)").font(.caption).foregroundStyle(.secondary)
            chart(cloudiness, color: .orange)
        }
    }

    private func chart(_ points: [[Double]], color: Color) -> some View {
        Chart(points.indices, id: \.self) { i in
            LineMark(x: .value("Seconds", points[i][0]), y: .value("Value", points[i][1]))
                .foregroundStyle(color)
                .interpolationMethod(.monotone)
        }
        .chartXAxisLabel("seconds")
        .frame(height: 100)
    }
}

/// What's happening right now: each stage of the server's analysis.
struct ResearchFeed: View {
    let steps: [Step]
    let live: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(live ? "Analyzing" : "How this was checked").font(.headline)
            ForEach(steps.indices, id: \.self) { i in
                let latest = i == steps.count - 1
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    if live && latest {
                        ProgressView().controlSize(.small)
                    } else {
                        Image(systemName: steps[i].icon).foregroundStyle(.secondary).frame(width: 20)
                    }
                    Text(steps[i].text)
                        .font(.subheadline)
                        .foregroundStyle(latest ? Color.primary : Color.secondary)
                }
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
    }
}

extension ScanReport {
    var title: String {
        ["CONSISTENT": "Consistent", "CHECK": "Check", "WARNING": "Warning", "NO_REF": "No reference yet", "BAD_SCAN": "Retest"][verdict] ?? verdict
    }

    var icon: String {
        switch verdict {
        case "CONSISTENT": "checkmark.seal.fill"
        case "CHECK": "exclamationmark.triangle.fill"
        case "WARNING": "xmark.octagon.fill"
        case "BAD_SCAN": "arrow.clockwise.circle.fill"
        default: "questionmark.circle.fill"
        }
    }

    var color: Color {
        switch verdict {
        case "CONSISTENT": .green
        case "CHECK": .orange
        case "WARNING": .red
        default: .secondary
        }
    }
}

extension TestRecord {
    var name: String {
        let parts = [scan.label?.brand, scan.label?.product_name].compactMap { $0 }
        return parts.isEmpty ? "Unnamed sample" : parts.joined(separator: " · ")
    }
}

/// Full report for one test. Shown as a sheet after Analyze, and pushed from History.
struct ReportView: View {
    let record: TestRecord
    let confirm: (TestRecord) async throws -> ConfirmResult
    @State private var shareImage: Image?
    @State private var confirmNote: String?
    @State private var confirming = false

    var body: some View {
        if let report = record.scan.report {
            List {
                Section {
                    VStack(spacing: 8) {
                        Image(systemName: report.icon).font(.system(size: 56)).foregroundStyle(report.color)
                        Text(report.title).font(.title.bold())
                        Text(report.headline).font(.headline).multilineTextAlignment(.center)
                        Text(record.name).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
                        Text(record.date, format: .dateTime.month().day().hour().minute()).font(.caption).foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                    Text(report.summary)
                    if record.scan.status == "partial" {
                        ProgressView("Claude is writing the explanation…").font(.subheadline)
                    }
                }
                Section("Checks") {
                    check("Sample vs other scans", accuracy(report.accuracy.label), report.accuracy.note
                          + (report.accuracy.reference_synthetic ? " Reference includes simulated demo scans." : ""))
                    check("Quality", report.quality.label.capitalized, report.quality.issues.joined(separator: " "))
                    check("Public records", report.reputability.label == "unknown" ? "Not checked" : report.reputability.label.capitalized
                          + (report.reputability.score.map { " (\($0)/100)" } ?? ""), "")
                }
                if let absorbance = record.scan.qc?.series?.absorbance, let scatter = record.scan.qc?.series?.scatter {
                    Section("Sample") { DissolutionChart(absorbance: absorbance, cloudiness: scatter).padding(.vertical, 4) }
                }
                if !report.key_findings.isEmpty {
                    Section("Findings") { ForEach(report.key_findings, id: \.self) { Label($0, systemImage: "exclamationmark.circle") } }
                }
                if !report.advice.isEmpty {
                    Section("What to do") { ForEach(report.advice, id: \.self) { Label($0, systemImage: "arrow.right.circle") } }
                }
                Section("Public records") {
                    ForEach(report.reputability.findings.indices, id: \.self) { i in
                        let f = report.reputability.findings[i]
                        if let link = f.url.flatMap(URL.init(string:)) { Link(f.text, destination: link) } else { Text(f.text) }
                    }
                }
                if !report.citations.isEmpty {
                    Section("Sources") {
                        ForEach(report.citations.indices, id: \.self) { i in
                            let c = report.citations[i]
                            if let link = c.url.flatMap(URL.init(string:)), ["http", "https"].contains(link.scheme?.lowercased() ?? "") {
                                Link(destination: link) { Label(c.title ?? c.source, systemImage: "link") }
                            } else {
                                Label(c.title ?? c.source, systemImage: "doc.text")
                            }
                        }
                    }
                }
                if canConfirm || confirmNote != nil {
                    Section {
                        if canConfirm {
                            Button(confirming ? "Adding…" : "Yes, this is \(record.name)") {
                                confirming = true
                                Task {
                                    do {
                                        let r = try await confirm(record)
                                        confirmNote = r.held == true
                                            ? "Not added: \(r.reason ?? "this scan doesn't match the product's reference, so it was held for review.")"
                                            : "Added. This product now has \(r.n) confirmed scans."
                                    }
                                    catch { confirmNote = error.localizedDescription }
                                    confirming = false
                                }
                            }
                            .disabled(confirming)
                        }
                        if let confirmNote { Text(confirmNote).font(.subheadline).foregroundStyle(.secondary) }
                    } footer: {
                        Text("Confirming adds this scan to the community reference for this product, so the next person's test is compared against it.")
                    }
                }
                if !record.steps.isEmpty {
                    Section("How this was checked") {
                        ForEach(record.steps.indices, id: \.self) { i in
                            Label(record.steps[i].text, systemImage: record.steps[i].icon).font(.subheadline).foregroundStyle(.secondary)
                        }
                    }
                }
                Section {
                    Text("SuppBuddy is a screening tool, not a certified lab test or medical advice.").font(.footnote).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Report")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    if let shareImage {
                        ShareLink(item: shareImage, preview: SharePreview("SuppBuddy report: \(record.name)", image: shareImage))
                    }
                }
            }
            .task(id: record.scan.status) {
                let renderer = ImageRenderer(content: ShareCard(record: record))
                renderer.scale = 3
                shareImage = renderer.uiImage.map { Image(uiImage: $0) }
            }
        }
    }

    private var canConfirm: Bool {
        !record.scan.confirmed && record.scan.qc?.ok == true && record.scan.product_id != nil && record.scan.report?.verdict != "BAD_SCAN"
    }

    private func check(_ title: String, _ value: String, _ detail: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            LabeledContent(title, value: value)
            if !detail.isEmpty { Text(detail).font(.caption).foregroundStyle(.secondary) }
        }
    }

    private func accuracy(_ label: String) -> String {
        ["consistent": "Matches", "borderline": "Borderline", "inconsistent": "Doesn't match",
         "insufficient_data": "Not enough data", "not_measured": "Not measured"][label] ?? label
    }
}

/// The image people share: verdict, product, how the sample behaved, and the bottom line.
struct ShareCard: View {
    let record: TestRecord

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let report = record.scan.report {
                HStack(spacing: 10) {
                    Image(systemName: report.icon).font(.title).foregroundStyle(report.color)
                    Text(report.title).font(.title2.bold())
                    Spacer()
                    Text(record.date, format: .dateTime.month().day().year()).font(.caption).foregroundStyle(.secondary)
                }
                Text(record.name).font(.headline)
                if let absorbance = record.scan.qc?.series?.absorbance, let scatter = record.scan.qc?.series?.scatter {
                    DissolutionChart(absorbance: absorbance, cloudiness: scatter)
                }
                Text(report.summary).font(.subheadline)
            }
            Divider()
            Text("Tested with SuppBuddy · a screening tool, not a lab test or medical advice")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(20)
        .frame(width: 360)
        .background(Color.white)
        .environment(\.colorScheme, .light)
    }
}

struct HistoryView: View {
    @Binding var records: [TestRecord]
    let confirm: (TestRecord) async throws -> ConfirmResult

    var body: some View {
        List {
            ForEach(records) { r in
                NavigationLink { ReportView(record: r, confirm: confirm) } label: { HistoryRow(record: r) }
            }
            .onDelete { offsets in
                records.remove(atOffsets: offsets)
                History.save(records)
            }
        }
        .overlay {
            if records.isEmpty {
                ContentUnavailableView("No tests yet", systemImage: "testtube.2", description: Text("Finished analyses show up here."))
            }
        }
        .navigationTitle("History")
    }
}

struct HistoryRow: View {
    let record: TestRecord

    var body: some View {
        HStack(spacing: 12) {
            Color.clear.frame(width: 48, height: 48)
                .overlay {
                    if let data = record.thumbnail, let image = UIImage(data: data) {
                        Image(uiImage: image).resizable().scaledToFill()
                    } else {
                        Image(systemName: "testtube.2").foregroundStyle(.secondary)
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 2) {
                Text(record.name).font(.headline).lineLimit(1)
                Text(record.date, format: .dateTime.month().day().hour().minute()).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            if let report = record.scan.report { Image(systemName: report.icon).foregroundStyle(report.color) }
        }
    }
}

/// Where the backend runs. Stored on the phone, so switching laptops or ngrok addresses needs no rebuild.
struct SettingsView: View {
    @AppStorage("server") private var server = ""
    @AppStorage("apiToken") private var apiToken = ""
    @AppStorage("sampleMassMg") private var sampleMassMg = 500.0
    @AppStorage("sampleVolumeMl") private var sampleVolumeMl = 50.0
    @State private var result: String?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(Server.defaultURL, text: $server)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } header: {
                    Text("Server")
                } footer: {
                    Text("The laptop running the backend, like http://192.168.1.20:8000 on the same Wi-Fi, or an ngrok https address. Empty means \(Server.defaultURL), which works in the Simulator.")
                }
                Section {
                    SecureField("API token", text: $apiToken)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } header: {
                    Text("API token")
                } footer: {
                    Text("Only if the server's .env sets API_TOKEN (do that before it's reachable beyond the laptop). Sent with every request.")
                }
                Section {
                    Button("Test connection") { Task { result = await check() } }
                    if let result { Text(result).font(.subheadline) }
                }
                Section {
                    Stepper("Powder: \(Int(sampleMassMg)) mg", value: $sampleMassMg, in: 100...2000, step: 50)
                    Stepper("Water: \(Int(sampleVolumeMl)) mL", value: $sampleVolumeMl, in: 10...100, step: 5)
                    Button("Use the standard (500 mg in 50 mL)") { sampleMassMg = 500; sampleVolumeMl = 50 }
                } header: {
                    Text("Sample prep")
                } footer: {
                    Text("Keep the standard unless you weighed a different amount. The server rescales color and cloudiness to the standard, so scans stay comparable.")
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }

    private func check() async -> String {
        do {
            let h = try await Server.health()
            return "Connected to \(Server.base). Claude explanations: " + ((h["llm"] as? Bool) == true ? "on." : "off (no API key in the server's .env).")
        } catch {
            return error.localizedDescription
        }
    }
}

/// The official NIH record found for the scanned barcode.
struct OfficialLabelCard: View {
    let label: OfficialLabel

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("NIH label database", systemImage: "building.columns")
                .font(.caption.bold())
                .foregroundStyle(.secondary)
            Text("\(label.brand) · \(label.product)").font(.subheadline.bold())
            if !label.ingredients.isEmpty {
                Text(label.ingredients.prefix(4).joined(separator: ", ")).font(.caption).foregroundStyle(.secondary)
            }
            HStack {
                Text(label.onMarket ? "On the market" : "Listed as discontinued")
                    .font(.caption.bold())
                    .foregroundStyle(label.onMarket ? Color.green : Color.orange)
                Spacer()
                if let url = URL(string: label.url) { Link("Official label", destination: url).font(.caption) }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.tertiarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))
    }
}

/// Live barcode scanner (VisionKit). Reports the first barcode it reads, once.
struct BarcodeScanner: UIViewControllerRepresentable {
    let onScan: (String) -> Void

    func makeUIViewController(context: Context) -> DataScannerViewController {
        let scanner = DataScannerViewController(recognizedDataTypes: [.barcode(symbologies: [.ean13, .ean8, .upce])], isHighlightingEnabled: true)
        scanner.delegate = context.coordinator
        DispatchQueue.main.async { try? scanner.startScanning() } // scanning can only start once the view is on screen
        return scanner
    }

    func updateUIViewController(_ scanner: DataScannerViewController, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(onScan: onScan) }

    @MainActor final class Coordinator: NSObject, DataScannerViewControllerDelegate {
        let onScan: (String) -> Void
        private var done = false
        init(onScan: @escaping (String) -> Void) { self.onScan = onScan }

        func dataScanner(_ scanner: DataScannerViewController, didAdd addedItems: [RecognizedItem], allItems: [RecognizedItem]) {
            guard !done else { return }
            for case let .barcode(code) in addedItems {
                guard let value = code.payloadStringValue else { continue }
                done = true
                scanner.stopScanning()
                onScan(value)
                return
            }
        }
    }
}

/// Camera on a real iPhone, photo library in the Simulator.
struct ImagePicker: UIViewControllerRepresentable {
    @Binding var image: UIImage?
    @Environment(\.dismiss) private var dismiss

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = UIImagePickerController.isSourceTypeAvailable(.camera) ? .camera : .photoLibrary
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ controller: UIImagePickerController, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: ImagePicker
        init(_ parent: ImagePicker) { self.parent = parent }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            parent.image = info[.originalImage] as? UIImage
            parent.dismiss()
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { parent.dismiss() }
    }
}
