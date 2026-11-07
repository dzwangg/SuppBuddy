import CoreBluetooth
import Observation

/// The SupPal tester over BLE, using the Nordic UART Service and protocol v2 (README, "BLE contract").
/// "b" -> dark + water-blank lines, "s" -> one sample line per second then "E", "L|..|.." -> tester screen.
@MainActor @Observable
final class Device: NSObject {
    var status = "Starting Bluetooth…"
    var isReady = false
    var id = "sim-ios"

    static let service = CBUUID(string: "6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
    static let rxUUID = CBUUID(string: "6E400002-B5A3-F393-E0A9-E50E24DCCA9E") // app -> tester
    static let txUUID = CBUUID(string: "6E400003-B5A3-F393-E0A9-E50E24DCCA9E") // tester -> app

    @ObservationIgnored private var central: CBCentralManager?
    @ObservationIgnored private var peripheral: CBPeripheral?
    @ObservationIgnored private var rx: CBCharacteristic?
    @ObservationIgnored private var buffer = ""
    @ObservationIgnored private var lines: AsyncThrowingStream<DeviceLine, Error>.Continuation?
    @ObservationIgnored private var lastLine = Date()
    @ObservationIgnored private var commandID = 0

    #if targetEnvironment(simulator)
    // ponytail: the Simulator has no Bluetooth, so the fake tester replays the backend's simulator
    // (GET /dev/readings), alternating genuine and cornstarch-cut vitamin C to show both outcomes.
    @ObservationIgnored private var runs = 0

    override init() {
        super.init()
        status = "Simulated tester"
        isReady = true
    }

    func measureBlank() async throws -> (dark: Snapshot, blank: Snapshot) {
        let r = try await Server.devReadings(profile: "vitamin_c")
        guard let blank = r.blank["white"] else { throw AppError("Simulated readings had no blank.") }
        return (r.dark, blank)
    }

    func runSample(onSample: (Sample) -> Void) async throws -> [Sample] {
        defer { runs += 1 }
        let r = try await Server.devReadings(profile: runs % 2 == 0 ? "vitamin_c" : "vitamin_c_cornstarch")
        for s in r.samples {
            onSample(s)
            try await Task.sleep(for: .milliseconds(40))
        }
        return r.samples
    }

    func show(_ lcd: Lcd) {}
    #else
    override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: nil)
    }

    /// Dark (LEDs off) and water-blank readings.
    func measureBlank() async throws -> (dark: Snapshot, blank: Snapshot) {
        var dark: Snapshot?, blank: Snapshot?
        for try await line in try command("b") {
            if case .dark(let d) = line { dark = d }
            if case .blank(let b) = line { blank = b }
            if let dark, let blank {
                finish(nil)
                return (dark, blank)
            }
        }
        throw AppError("Tester didn't send a blank reading.")
    }

    /// One sample run (about a minute on the tester). Calls onSample as each reading arrives.
    func runSample(onSample: (Sample) -> Void) async throws -> [Sample] {
        var samples: [Sample] = []
        for try await line in try command("s") {
            if case .sample(let s) = line {
                samples.append(s)
                onSample(s)
            }
        }
        return samples
    }

    /// Shows the verdict on the tester's screen.
    func show(_ lcd: Lcd) {
        guard let peripheral, let rx else { return }
        let text = ["L", lcd.line1, lcd.line2].map { $0.trimmingCharacters(in: .whitespaces) }.joined(separator: "|")
        peripheral.writeValue(Data(text.utf8), for: rx, type: rx.properties.contains(.write) ? .withResponse : .withoutResponse)
    }

    private func command(_ c: String) throws -> AsyncThrowingStream<DeviceLine, Error> {
        guard let peripheral, let rx else { throw AppError("Tester not connected.") }
        guard lines == nil else { throw AppError("Tester is busy.") }
        let (stream, continuation) = AsyncThrowingStream<DeviceLine, Error>.makeStream()
        lines = continuation
        buffer = ""
        lastLine = .now
        commandID += 1
        let id = commandID
        Task { // the tester sends a line at least every second while it works
            while commandID == id, lines != nil {
                try? await Task.sleep(for: .seconds(1))
                if commandID == id, Date.now.timeIntervalSince(lastLine) > 5 { finish(AppError("Tester stopped responding.")) }
            }
        }
        peripheral.writeValue(Data(c.utf8), for: rx, type: rx.properties.contains(.write) ? .withResponse : .withoutResponse)
        return stream
    }
    #endif

    private func finish(_ error: Error?) {
        let continuation = lines
        lines = nil
        if let error { continuation?.finish(throwing: error) } else { continuation?.finish() }
    }

    private func scan() {
        status = "Looking for tester…"
        central?.scanForPeripherals(withServices: [Self.service])
    }

    private func lost() {
        peripheral = nil
        rx = nil
        isReady = false
        finish(AppError("Tester disconnected."))
        scan()
    }
}

extension Device: @preconcurrency CBCentralManagerDelegate, @preconcurrency CBPeripheralDelegate {
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        switch central.state {
        case .poweredOn: scan()
        case .poweredOff: status = "Turn Bluetooth on."
        case .unauthorized: status = "Allow Bluetooth for SupPal in Settings."
        default: status = "Bluetooth unavailable."
        }
    }

    func centralManager(_ central: CBCentralManager, didDiscover p: CBPeripheral, advertisementData: [String: Any], rssi: NSNumber) {
        central.stopScan()
        peripheral = p
        p.delegate = self
        status = "Connecting to \(p.name ?? "tester")…"
        central.connect(p)
    }

    func centralManager(_ central: CBCentralManager, didConnect p: CBPeripheral) {
        id = "esp32-" + (p.name ?? String(p.identifier.uuidString.prefix(8)))
        p.discoverServices([Self.service])
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect p: CBPeripheral, error: Error?) { lost() }
    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral p: CBPeripheral, error: Error?) { lost() }

    func peripheral(_ p: CBPeripheral, didDiscoverServices error: Error?) {
        for s in p.services ?? [] { p.discoverCharacteristics([Self.rxUUID, Self.txUUID], for: s) }
    }

    func peripheral(_ p: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        for c in service.characteristics ?? [] {
            if c.uuid == Self.rxUUID { rx = c }
            if c.uuid == Self.txUUID { p.setNotifyValue(true, for: c) }
        }
        isReady = rx != nil
        status = isReady ? "Connected to \(p.name ?? "tester")" : "Tester firmware is missing the RX characteristic."
    }

    func peripheral(_ p: CBPeripheral, didUpdateValueFor c: CBCharacteristic, error: Error?) {
        guard let data = c.value, let chunk = String(data: data, encoding: .utf8) else { return }
        buffer += chunk
        for line in takeLines(&buffer) {
            lastLine = .now
            guard let parsed = DeviceLine(line) else {
                finish(AppError("Unexpected line from tester: \(line). Is it running protocol v2 firmware?"))
                return
            }
            lines?.yield(parsed)
            if parsed == .end { finish(nil) }
        }
    }
}
