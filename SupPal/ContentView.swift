import Charts
import SwiftUI
import Vision
import VisionKit

struct ContentView: View {
    @State private var device = Device()
    @State private var blank: [Double]?
    @State private var spectrum: [Double]?
    @State private var matches: [Match] = []
    @State private var label: UIImage?
    @State private var showPicker = false
    @State private var busy: String?
    @State private var error: String?
    @State private var record: TestRecord?
    @State private var showReport = false
    @State private var steps: [Step] = []
    @State private var history = History.load()
    @State private var barcode: String?
    @State private var official: OfficialLabel?
    @State private var barcodeNote: String?
    @State private var lookingUp = false
    @State private var showScanner = false
    @State private var typingBarcode = false
    @State private var typedCode = ""

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(spacing: 16) {
                        statusPill

                        StepCard(number: 1, title: "Water blank", detail: "Fill the cuvette with clean water, insert it, then measure.", done: blank != nil) {
                            Button(blank == nil ? "Measure blank" : "Re-measure blank") {
                                run("Measuring blank…") { blank = try await device.measure(); spectrum = nil; matches = []; steps = [] }
                            }
                            .buttonStyle(.bordered)
                            .disabled(!device.isReady)
                        }

                        StepCard(number: 2, title: "Sample", detail: "Dissolve the supplement in water, insert the cuvette, then measure.", done: spectrum != nil) {
                            Button("Measure sample") {
                                run("Measuring sample…") {
                                    let sample = try await device.measure()
                                    guard let blank, let a = absorbance(sample: sample, blank: blank) else {
                                        throw AppError("Channel count changed. Re-measure the blank.")
                                    }
                                    spectrum = a
                                    matches = topMatches(a, in: Reference.all)
                                    steps = []
                                }
                            }
                            .buttonStyle(.bordered)
                            .disabled(blank == nil || !device.isReady)
                            if let spectrum {
                                SpectrumChart(spectrum: spectrum, match: matches.first)
                                ForEach(matches, id: \.reference.product) { MatchRow(match: $0) }
                            }
                        }

                        StepCard(number: 3, title: "Label", detail: "Photograph the label, then scan its barcode to compare with the official NIH record.", done: label != nil) {
                            Button(label == nil ? "Photograph label" : "Retake photo") { showPicker = true }
                                .buttonStyle(.bordered)
                            if let label {
                                Color.clear.frame(height: 160)
                                    .overlay { Image(uiImage: label).resizable().scaledToFill() }
                                    .clipShape(RoundedRectangle(cornerRadius: 12))
                            }
                            Button(barcode == nil ? "Scan barcode" : "Rescan barcode", systemImage: "barcode.viewfinder") { scanBarcode() }
                                .buttonStyle(.bordered)
                                .disabled(lookingUp)
                            if lookingUp { ProgressView("Checking the NIH label database…").font(.subheadline) }
                            if let official { OfficialLabelCard(label: official) }
                            if let barcodeNote { Text(barcodeNote).font(.subheadline).foregroundStyle(.secondary) }
                        }

                        analyzeSection

                        Text("SupPal is a screening tool, not a certified lab test or medical advice.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                            .id("bottom")
                    }
                    .padding()
                    .disabled(busy != nil)
                }
                .onChange(of: steps.count) { withAnimation { proxy.scrollTo("bottom", anchor: .bottom) } }
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("SupPal")
            .toolbar {
                NavigationLink { HistoryView(records: $history) } label: {
                    Label("History", systemImage: "clock.arrow.circlepath")
                }
            }
            .sheet(isPresented: $showPicker) { ImagePicker(image: $label).ignoresSafeArea() }
            .sheet(isPresented: $showScanner) {
                BarcodeScanner { code in
                    showScanner = false
                    lookUp(code)
                }
                .ignoresSafeArea()
            }
            .alert("Enter the barcode number", isPresented: $typingBarcode) {
                TextField("12-digit UPC", text: $typedCode).keyboardType(.numberPad)
                Button("Look up") { lookUp(typedCode) }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("The camera scanner isn't available here, so type the digits printed under the barcode.")
            }
            .sheet(isPresented: $showReport) {
                if let record {
                    NavigationStack {
                        ReportView(record: record)
                            .toolbar {
                                ToolbarItem(placement: .cancellationAction) { Button("Done") { showReport = false } }
                            }
                    }
                }
            }
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
            Button {
                guard let label, let spectrum else { return }
                steps = [Step(icon: "paperplane", text: "Sending the label photo and spectrum to Claude")]
                run("Analyzing…") {
                    let report = try await Agent.analyze(labelJPEG: jpeg(label, maxSide: 1568), spectrum: spectrum, matches: matches,
                                                         barcode: barcode, official: official) { step in
                        withAnimation { steps.append(step) }
                    }
                    let done = TestRecord(date: .now, report: report, spectrum: spectrum, match: matches.first,
                                          steps: steps, thumbnail: jpeg(label, maxSide: 240), official: official)
                    record = done
                    history.insert(done, at: 0)
                    History.save(history)
                    showReport = true
                }
            } label: {
                Label("Analyze", systemImage: "sparkles").font(.headline).frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(spectrum == nil || label == nil || lookingUp)

            if let busy, steps.isEmpty { ProgressView(busy).font(.subheadline) }
            if !steps.isEmpty { ResearchFeed(steps: steps, live: busy != nil) }
            if let error { Text(error).font(.subheadline).foregroundStyle(.red) }
            if record != nil, busy == nil {
                Button("View last report") { showReport = true }
            }
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
        barcode = code
        official = nil
        barcodeNote = nil
        lookingUp = true
        Task {
            do {
                official = try await NIH.lookup(barcode: code)
                if official == nil { barcodeNote = "Barcode \(code) isn't in the NIH label database. Many products aren't." }
            } catch {
                barcode = nil
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

/// Sample absorbance as bars (violet = shortest wavelength channel, red = longest),
/// with the best database match drawn as a line.
struct SpectrumChart: View {
    let spectrum: [Double]
    let match: Match?

    var body: some View {
        let ref = fitted
        VStack(alignment: .leading, spacing: 6) {
            Chart {
                ForEach(spectrum.indices, id: \.self) { i in
                    BarMark(x: .value("Channel", "\(i + 1)"), y: .value("Absorbance", spectrum[i]))
                        .foregroundStyle(color(i))
                        .cornerRadius(4)
                }
                ForEach(ref.indices, id: \.self) { i in
                    LineMark(x: .value("Channel", "\(i + 1)"), y: .value("Absorbance", ref[i]))
                        .foregroundStyle(Color.primary)
                        .interpolationMethod(.catmullRom)
                    PointMark(x: .value("Channel", "\(i + 1)"), y: .value("Absorbance", ref[i]))
                        .foregroundStyle(Color.primary)
                        .symbolSize(20)
                }
            }
            .chartYAxisLabel("Absorbance")
            .frame(height: 180)
            if let match, !ref.isEmpty {
                Text("Bars: your sample · Line: \(match.reference.product), scaled to fit")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true) // wrap instead of truncating in the share image
            }
        }
    }

    /// Best match scaled onto the sample (least squares). Matching compares shape, so this lines the shapes up.
    private var fitted: [Double] {
        guard let r = match?.reference.absorbance, r.count == spectrum.count else { return [] }
        let rr = r.map { $0 * $0 }.reduce(0, +)
        guard rr > 0 else { return [] }
        let k = zip(spectrum, r).map(*).reduce(0, +) / rr
        return r.map { $0 * k }
    }

    private func color(_ i: Int) -> Color {
        let t = spectrum.count > 1 ? Double(i) / Double(spectrum.count - 1) : 0
        return Color(hue: 0.75 * (1 - t), saturation: 0.75, brightness: 0.9)
    }
}

/// What Claude is doing right now: its notes, each search, and the sites it read.
struct ResearchFeed: View {
    let steps: [Step]
    let live: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(live ? "Researching" : "How this was checked").font(.headline)
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

struct MatchRow: View {
    let match: Match

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(match.reference.product).font(.subheadline)
                Spacer()
                Text("\(Int((match.similarity * 100).rounded()))%")
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            ProgressView(value: min(max(match.similarity, 0), 1)) // noisy data can go negative
        }
    }
}

extension Report {
    var icon: String {
        switch verdict {
        case "consistent": "checkmark.seal.fill"
        case "questionable": "exclamationmark.triangle.fill"
        case "concerning": "xmark.octagon.fill"
        default: "questionmark.circle.fill"
        }
    }

    var color: Color {
        switch verdict {
        case "consistent": .green
        case "questionable": .orange
        case "concerning": .red
        default: .secondary
        }
    }
}

/// Full report for one test. Shown as a sheet after Analyze, and pushed from History.
struct ReportView: View {
    let record: TestRecord
    @State private var shareImage: Image?
    private var report: Report { record.report }

    var body: some View {
        List {
            Section {
                VStack(spacing: 8) {
                    Image(systemName: report.icon).font(.system(size: 56)).foregroundStyle(report.color)
                    Text(report.verdict.capitalized).font(.title.bold())
                    Text(report.brand).font(.headline).multilineTextAlignment(.center)
                    Text(report.product)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .lineLimit(3)
                    Text(record.date, format: .dateTime.month().day().hour().minute())
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 8)
                Text(report.summary)
            }
            Section("Spectrum") {
                SpectrumChart(spectrum: record.spectrum, match: record.match).padding(.vertical, 4)
                Text(report.spectrumMatch)
            }
            if let check = report.labelCheck {
                Section("Official label check") {
                    Text(check)
                    if let o = record.official, let url = URL(string: o.url) {
                        Link(destination: url) { Label("NIH record: \(o.brand) \(o.product)", systemImage: "building.columns") }
                    }
                }
            }
            Section("Brand reputation") { Text(report.reputation) }
            if !report.concerns.isEmpty {
                Section("Concerns") {
                    ForEach(report.concerns, id: \.self) { Label($0, systemImage: "exclamationmark.circle").foregroundStyle(.primary) }
                }
            }
            if !report.sources.isEmpty {
                Section("Sources") {
                    ForEach(report.sources, id: \.url) { s in
                        if let url = URL(string: s.url) { Link(destination: url) { Label(s.title, systemImage: "link") } }
                    }
                }
            }
            if !record.steps.isEmpty {
                Section("How this was checked") {
                    ForEach(record.steps.indices, id: \.self) { i in
                        Label(record.steps[i].text, systemImage: record.steps[i].icon)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            Section {
                Text("SupPal is a screening tool, not a certified lab test or medical advice.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Report")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                if let shareImage {
                    ShareLink(item: shareImage, preview: SharePreview("SupPal report: \(report.brand)", image: shareImage))
                }
            }
        }
        .task {
            let renderer = ImageRenderer(content: ShareCard(record: record))
            renderer.scale = 3
            shareImage = renderer.uiImage.map { Image(uiImage: $0) }
        }
    }
}

/// The image people share: verdict, product, spectrum and the bottom line.
struct ShareCard: View {
    let record: TestRecord

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                Image(systemName: record.report.icon).font(.title).foregroundStyle(record.report.color)
                Text(record.report.verdict.capitalized).font(.title2.bold())
                Spacer()
                Text(record.date, format: .dateTime.month().day().year()).font(.caption).foregroundStyle(.secondary)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(record.report.brand).font(.headline)
                Text(record.report.product).font(.subheadline).foregroundStyle(.secondary).lineLimit(2)
            }
            SpectrumChart(spectrum: record.spectrum, match: record.match)
            Text(record.report.summary).font(.subheadline)
            Divider()
            Text("Tested with SupPal · a screening tool, not a lab test or medical advice")
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

    var body: some View {
        List {
            ForEach(records) { r in
                NavigationLink { ReportView(record: r) } label: { HistoryRow(record: r) }
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
                    if let image = UIImage(data: record.thumbnail) {
                        Image(uiImage: image).resizable().scaledToFill()
                    } else {
                        Image(systemName: "photo").foregroundStyle(.secondary)
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 2) {
                Text(record.report.brand).font(.headline).lineLimit(1)
                Text(record.date, format: .dateTime.month().day().hour().minute())
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Image(systemName: record.report.icon).foregroundStyle(record.report.color)
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
