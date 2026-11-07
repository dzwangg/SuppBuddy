import CoreBluetooth
import Observation

/// The SupPal tester over BLE, using the Nordic UART Service (see README, "BLE contract").
/// App writes "m"; tester notifies one line of comma-separated raw channel readings ending in "\n".
@MainActor @Observable
final class Device: NSObject {
    var status = "Starting Bluetooth…"
    var isReady = false

    static let service = CBUUID(string: "6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
    static let rxUUID = CBUUID(string: "6E400002-B5A3-F393-E0A9-E50E24DCCA9E") // app -> tester
    static let txUUID = CBUUID(string: "6E400003-B5A3-F393-E0A9-E50E24DCCA9E") // tester -> app

    @ObservationIgnored private var central: CBCentralManager?
    @ObservationIgnored private var peripheral: CBPeripheral?
    @ObservationIgnored private var rx: CBCharacteristic?
    @ObservationIgnored private var buffer = ""
    @ObservationIgnored private var pending: CheckedContinuation<[Double], Error>?
    @ObservationIgnored private var requestID = 0

    #if targetEnvironment(simulator)
    // ponytail: the Simulator has no Bluetooth. Alternates blank/sample readings shaped like the riboflavin demo reference.
    @ObservationIgnored private var mockCalls = 0

    override init() {
        super.init()
        status = "Simulated tester"
        isReady = true
    }

    func measure() async throws -> [Double] {
        try await Task.sleep(for: .milliseconds(400))
        let blank: [Double] = [3100, 3400, 3650, 3900, 4100, 4000, 3800, 3500]
        let a: [Double] = [0.61, 0.93, 0.72, 0.19, 0.05, 0.03, 0.02, 0.02]
        defer { mockCalls += 1 }
        return mockCalls % 2 == 0 ? blank : zip(blank, a).map { $0 * pow(10, -$1) }
    }
    #else
    override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: nil)
    }

    func measure() async throws -> [Double] {
        guard let peripheral, let rx else { throw AppError("Tester not connected.") }
        guard pending == nil else { throw AppError("Already measuring.") }
        requestID += 1
        let id = requestID
        Task {
            try? await Task.sleep(for: .seconds(5))
            if requestID == id { finish(.failure(AppError("Tester didn't answer within 5 s."))) }
        }
        return try await withCheckedThrowingContinuation { continuation in
            pending = continuation
            buffer = ""
            peripheral.writeValue(Data("m".utf8), for: rx, type: rx.properties.contains(.write) ? .withResponse : .withoutResponse)
        }
    }
    #endif

    private func finish(_ result: Result<[Double], Error>) {
        let continuation = pending
        pending = nil
        continuation?.resume(with: result)
    }

    private func scan() {
        status = "Looking for tester…"
        central?.scanForPeripherals(withServices: [Self.service])
    }

    private func lost() {
        peripheral = nil
        rx = nil
        isReady = false
        finish(.failure(AppError("Tester disconnected.")))
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
            finish(parseReading(line).map { .success($0) } ?? .failure(AppError("Bad reading from tester: \(line)")))
        }
    }
}
