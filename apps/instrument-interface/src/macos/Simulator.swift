// Owned synthetic AppKit fixture. No network, serial, instrument or shell APIs.
import AppKit

final class Simulator: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var controller: NSWindowController!
    let count = NSTextField(string: "1")
    let status = NSTextField(labelWithString: "Ready")
    let result = NSTextField(labelWithString: "No result")

    func label(_ text: String, _ identifier: String) -> NSTextField {
        let field = NSTextField(labelWithString: text)
        field.setAccessibilityIdentifier(identifier)
        return field
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        window = NSWindow(contentRect: NSRect(x: 120, y: 120, width: 560, height: 420),
                          styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "Airalogy Native Reader — Simulation"
        window.setAccessibilityIdentifier("reader.window")
        window.setAccessibilityElement(true)
        window.isReleasedWhenClosed = false
        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 16
        stack.translatesAutoresizingMaskIntoConstraints = false
        stack.addArrangedSubview(label("Airalogy Native Reader 1.0 — simulation only", "app.identity"))
        stack.addArrangedSubview(label("Synthetic sample count", "sample.label"))
        count.setAccessibilityIdentifier("sample.count")
        count.widthAnchor.constraint(equalToConstant: 200).isActive = true
        stack.addArrangedSubview(count)
        let run = NSButton(title: "Run simulation", target: self, action: #selector(runSimulation))
        run.setAccessibilityIdentifier("run.simulation")
        stack.addArrangedSubview(run)
        status.setAccessibilityIdentifier("reader.status")
        result.setAccessibilityIdentifier("reader.result")
        stack.addArrangedSubview(status)
        stack.addArrangedSubview(result)
        stack.addArrangedSubview(label("SYNTHETIC_PRIVATE_NOTE_DO_NOT_CAPTURE", "private.note"))
        let password = NSSecureTextField(string: "SYNTHETIC_PASSWORD_DO_NOT_CAPTURE")
        password.setAccessibilityIdentifier("private.password")
        password.widthAnchor.constraint(equalToConstant: 200).isActive = true
        stack.addArrangedSubview(password)
        window.contentView!.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: window.contentView!.trailingAnchor, constant: -24),
            stack.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 24),
        ])
        controller = NSWindowController(window: window)
        controller.showWindow(nil)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        NSAccessibility.post(element: window!, notification: .windowCreated)
        // Only owned-fixture readiness, never vendor application or research data.
        print("SIMULATOR_READY \(window.windowNumber) \(window.isVisible) \(window.accessibilityRole()?.rawValue ?? "none")")
        fflush(stdout)
    }

    @objc func runSimulation() {
        guard let value = Int(count.stringValue), (1...10).contains(value) else {
            status.stringValue = "Invalid sample count"; return
        }
        result.stringValue = String(format: "%.2f", Double(value) * 0.42)
        status.stringValue = "Complete"
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

let app = NSApplication.shared
let delegate = Simulator()
app.delegate = delegate
app.setActivationPolicy(.regular)
// NSApplication holds its delegate weakly. Keep the programmatic fixture and
// its window/controller alive for the complete optimized executable lifetime.
withExtendedLifetime(delegate) { app.run() }
