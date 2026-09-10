// Trusted, local Accessibility transport. No script evaluation, shell, coordinates,
// screenshots or arbitrary attribute/action names are accepted from callers.
import AppKit
import ApplicationServices
import CryptoKit
import Darwin
import Foundation
import Security

// Replaced only by the trusted local builder after signing its owned simulator.
// Direct compilation keeps non-hash placeholders and cannot authorize writes.
let ownedSimulatorHash = "__AIRALOGY_OWNED_SIMULATOR_SHA256__"
let ownedSimulatorInfoHash = "__AIRALOGY_OWNED_SIMULATOR_INFO_SHA256__"

enum Refusal: String, Error {
    case invalidRequest = "invalid_request"
    case permissionRequired = "accessibility_permission_required"
    case targetChanged = "target_changed"
    case windowChanged = "selected_window_changed"
    case windowCount = "requires_one_window"
    case windowTitle = "window_title_changed"
    case windowHidden = "window_hidden_or_unmeasurable"
    case privateRegionMissing = "private_region_missing_or_ambiguous"
    case unexpectedDialog = "unexpected_dialog"
    case unsupported = "unsupported_target"
    case boundExceeded = "bound_exceeded"
    case accessibilityFailure = "accessibility_failure"
    case simulationOnly = "owned_simulation_required"
    case staleObservation = "stale_observation"
    case focusChanged = "selected_window_not_focused"
    case controlChanged = "selected_control_changed"
}

func exact(_ value: [String: Any], _ keys: Set<String>) throws {
    guard Set(value.keys) == keys else { throw Refusal.invalidRequest }
}

func string(_ value: Any?, limit: Int = 512, empty: Bool = false) throws -> String {
    guard let text = value as? String, text.utf8.count <= limit,
          empty || !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
          !text.unicodeScalars.contains(where: { $0.value < 32 && ![9, 10, 13].contains($0.value) })
    else { throw Refusal.invalidRequest }
    return text
}

func number(_ value: Any?, low: Int, high: Int) throws -> Int {
    guard let number = value as? NSNumber,
          CFGetTypeID(number) != CFBooleanGetTypeID(),
          number.doubleValue.isFinite,
          number.doubleValue == Double(number.intValue),
          (low...high).contains(number.intValue)
    else { throw Refusal.invalidRequest }
    return number.intValue
}

func fileHash(_ url: URL) throws -> String {
    let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
    guard values.isRegularFile == true, values.isSymbolicLink != true,
          let size = values.fileSize, size > 0, size <= 268_435_456
    else { throw Refusal.unsupported }
    let handle = try FileHandle(forReadingFrom: url)
    defer { try? handle.close() }
    var hash = SHA256()
    var bytes = 0
    while let chunk = try handle.read(upToCount: 65_536), !chunk.isEmpty {
        bytes += chunk.count
        guard bytes <= size else { throw Refusal.targetChanged }
        hash.update(data: chunk)
    }
    guard bytes == size else { throw Refusal.targetChanged }
    return hash.finalize().map { String(format: "%02x", $0) }.joined()
}

func physicalPath(_ path: String) throws -> String {
    guard let resolved = realpath(path, nil) else { throw Refusal.unsupported }
    defer { free(resolved) }
    return String(cString: resolved)
}

func bundleIdentity(_ path: String) throws -> [String: Any] {
    guard path.hasPrefix("/"), path.hasSuffix(".app") else { throw Refusal.invalidRequest }
    let url = URL(fileURLWithPath: path)
    // Foundation rewrites /private/tmp to /tmp on macOS. Use POSIX realpath
    // consistently with the Node host, including NSRunningApplication URLs.
    guard try physicalPath(path) == path,
          let bundle = Bundle(url: url), let executable = bundle.executableURL,
          try physicalPath(executable.path).hasPrefix(path + "/Contents/MacOS/"),
          let identifier = bundle.bundleIdentifier,
          let version = bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
    else { throw Refusal.unsupported }
    var code: SecStaticCode?
    guard SecStaticCodeCreateWithPath(url as CFURL, [], &code) == errSecSuccess,
          let code,
          SecStaticCodeCheckValidity(code, SecCSFlags(rawValue: kSecCSStrictValidate | kSecCSCheckAllArchitectures), nil) == errSecSuccess
    else { throw Refusal.unsupported }
    var signing: CFDictionary?
    guard SecCodeCopySigningInformation(code, SecCSFlags(rawValue: kSecCSSigningInformation), &signing) == errSecSuccess,
          let data = signing as? [String: Any], let cdhash = data[kSecCodeInfoUnique as String] as? Data
    else { throw Refusal.unsupported }
    return ["bundle_path": path, "bundle_id": try string(identifier), "version": try string(version),
            "executable_path": try physicalPath(executable.path), "executable_sha256": try fileHash(executable),
            "code_directory_hash": cdhash.map { String(format: "%02x", $0) }.joined(),
            "info_sha256": try fileHash(url.appendingPathComponent("Contents/Info.plist"))]
}

func processIdentity(_ pid: pid_t, bundle: [String: Any]) throws -> [String: Any] {
    var info = proc_bsdinfo()
    let count = proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &info, Int32(MemoryLayout<proc_bsdinfo>.size))
    guard count == MemoryLayout<proc_bsdinfo>.size, info.pbi_uid == geteuid(),
          let app = NSRunningApplication(processIdentifier: pid), !app.isTerminated,
          app.isFinishedLaunching,
          let bundleURL = app.bundleURL, let executableURL = app.executableURL,
          try physicalPath(bundleURL.path) == bundle["bundle_path"] as? String,
          try physicalPath(executableURL.path) == bundle["executable_path"] as? String,
          app.bundleIdentifier == bundle["bundle_id"] as? String
    else { throw Refusal.targetChanged }
    return ["pid": Int(pid), "uid": Int(info.pbi_uid),
            "started_seconds": String(info.pbi_start_tvsec), "started_microseconds": String(info.pbi_start_tvusec)]
}

func sameJSON(_ left: Any, _ right: Any) throws -> Bool {
    try JSONSerialization.data(withJSONObject: left, options: [.sortedKeys]) ==
        JSONSerialization.data(withJSONObject: right, options: [.sortedKeys])
}

func pinnedApplication(_ pin: [String: Any]) throws -> AXUIElement {
    try exact(pin, ["bundle", "process"])
    guard let bundle = pin["bundle"] as? [String: Any],
          let process = pin["process"] as? [String: Any]
    else { throw Refusal.invalidRequest }
    let currentBundle = try bundleIdentity(string(bundle["bundle_path"], limit: 4096))
    let pid = pid_t(try number(process["pid"], low: 1, high: Int(Int32.max)))
    guard try sameJSON(bundle, currentBundle), try sameJSON(process, processIdentity(pid, bundle: currentBundle))
    else { throw Refusal.targetChanged }
    guard AXIsProcessTrusted() else { throw Refusal.permissionRequired }
    // This changes only this transport process's IPC timeout, not system settings.
    guard AXUIElementSetMessagingTimeout(AXUIElementCreateSystemWide(), 2) == .success
    else { throw Refusal.accessibilityFailure }
    return AXUIElementCreateApplication(pid)
}

func attribute(_ element: AXUIElement, _ name: CFString) throws -> CFTypeRef? {
    var value: CFTypeRef?
    let result = AXUIElementCopyAttributeValue(element, name, &value)
    if result == .attributeUnsupported || result == .noValue { return nil }
    guard result == .success else { throw Refusal.accessibilityFailure }
    return value
}

func elements(_ element: AXUIElement, _ name: CFString, limit: Int) throws -> [AXUIElement] {
    var count: CFIndex = 0
    let result = AXUIElementGetAttributeValueCount(element, name, &count)
    if result == .attributeUnsupported || result == .noValue { return [] }
    guard result == .success else { throw Refusal.accessibilityFailure }
    guard count >= 0, count <= limit else { throw Refusal.boundExceeded }
    if count == 0 { return [] }
    var values: CFArray?
    guard AXUIElementCopyAttributeValues(element, name, 0, count, &values) == .success,
          let values = values as? [AXUIElement], values.count == count
    else { throw Refusal.accessibilityFailure }
    return values
}

func axText(_ element: AXUIElement, _ name: String, limit: Int = 512) throws -> String? {
    guard let raw = try attribute(element, name as CFString) else { return nil }
    guard let text = raw as? String else { throw Refusal.unsupported }
    return try string(text, limit: limit, empty: true)
}

func axBool(_ element: AXUIElement, _ name: String) throws -> Bool? {
    guard let value = try attribute(element, name as CFString) else { return nil }
    guard CFGetTypeID(value) == CFBooleanGetTypeID(), let boolean = value as? Bool
    else { throw Refusal.unsupported }
    return boolean
}

func frame(_ element: AXUIElement) throws -> CGRect? {
    guard let position = try attribute(element, kAXPositionAttribute as CFString),
          let size = try attribute(element, kAXSizeAttribute as CFString),
          CFGetTypeID(position) == AXValueGetTypeID(), CFGetTypeID(size) == AXValueGetTypeID()
    else { return nil }
    var point = CGPoint.zero
    var extent = CGSize.zero
    guard AXValueGetValue(unsafeBitCast(position, to: AXValue.self), .cgPoint, &point),
          AXValueGetValue(unsafeBitCast(size, to: AXValue.self), .cgSize, &extent),
          point.x.isFinite, point.y.isFinite, extent.width.isFinite, extent.height.isFinite,
          extent.width > 0, extent.height > 0
    else { return nil }
    return CGRect(origin: point, size: extent)
}

struct Node {
    let element: AXUIElement
    let parent: Int?
    let role: String
    let identifier: String?
    let secure: Bool
}

struct Capture {
    let report: [String: Any]
    let controls: [String: AXUIElement]
    let application: AXUIElement
    let window: AXUIElement
}

func jsonKey(_ value: Any) throws -> String {
    String(data: try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]), encoding: .utf8)!
}

func capture(_ request: [String: Any]) throws -> Capture {
    try exact(request, ["operation", "pin", "window_title", "capture_values", "redact_identifiers"])
    guard let pin = request["pin"] as? [String: Any],
          let capture = request["capture_values"] as? NSNumber,
          CFGetTypeID(capture) == CFBooleanGetTypeID(),
          let masks = request["redact_identifiers"] as? [String], masks.count <= 32,
          Set(masks).count == masks.count
    else { throw Refusal.invalidRequest }
    for mask in masks { _ = try string(mask) }
    let title = try string(request["window_title"])
    let app = try pinnedApplication(pin)
    let windows = try elements(app, kAXWindowsAttribute as CFString, limit: 8)
    guard windows.count == 1, let window = windows.first else { throw Refusal.windowCount }
    guard try axText(window, kAXRoleAttribute) == "AXWindow",
          try axText(window, kAXTitleAttribute) == title else { throw Refusal.windowTitle }
    guard try axBool(window, kAXMinimizedAttribute) == false,
          let windowFrame = try frame(window) else { throw Refusal.windowHidden }
    var nodes: [Node] = []
    func visit(_ element: AXUIElement, parent: Int?, depth: Int) throws {
        guard nodes.count < 200, depth <= 16 else { throw Refusal.boundExceeded }
        let role = try axText(element, kAXRoleAttribute) ?? "AXUnknown"
        let subrole = try axText(element, kAXSubroleAttribute)
        guard !["AXSheet", "AXDialog", "AXSystemDialog"].contains(role),
              !["AXDialog", "AXSystemDialog"].contains(subrole ?? "")
        else { throw Refusal.unexpectedDialog }
        let index = nodes.count
        nodes.append(Node(element: element, parent: parent, role: role,
                          identifier: try axText(element, kAXIdentifierAttribute),
                          secure: subrole == "AXSecureTextField" || role == "AXSecureTextField"))
        for child in try elements(element, kAXChildrenAttribute as CFString, limit: 200 - nodes.count) {
            // AX trees may contain cycles or aliases. Refuse rather than double-target.
            guard !nodes.contains(where: { CFEqual($0.element, child) }) else { throw Refusal.unsupported }
            try visit(child, parent: index, depth: depth + 1)
        }
    }
    try visit(window, parent: nil, depth: 0)
    for mask in masks {
        guard nodes.filter({ $0.identifier == mask }).count == 1 else { throw Refusal.privateRegionMissing }
    }
    var hidden = Set<Int>()
    for (index, node) in nodes.enumerated() {
        if node.secure || masks.contains(node.identifier ?? "") { hidden.insert(index) }
        if let parent = node.parent, hidden.contains(parent) { hidden.insert(index) }
    }
    // Ancestor metadata may aggregate descendant values. Suppress it too.
    let privateCount = hidden.count
    for index in Array(hidden) {
        var ancestor = nodes[index].parent
        while let current = ancestor { hidden.insert(current); ancestor = nodes[current].parent }
    }
    let supported: Set<String> = ["AXStaticText", "AXTextField", "AXTextArea", "AXButton", "AXCheckBox", "AXRadioButton", "AXPopUpButton", "AXComboBox", "AXSlider", "AXTabGroup"]
    var controls: [[String: Any]] = []
    var addressable: [String: AXUIElement] = [:]
    for (index, node) in nodes.enumerated() where !hidden.contains(index) && supported.contains(node.role) {
        guard let bounds = try frame(node.element), bounds.intersects(windowFrame) else { continue }
        guard controls.count < 64 else { throw Refusal.boundExceeded }
        let editable = ["AXTextField", "AXTextArea", "AXComboBox"].contains(node.role)
        // Do not read titles/descriptions of inputs: applications can mirror values there.
        let label = try editable ? (node.identifier ?? node.role) :
            (axText(node.element, kAXTitleAttribute) ?? axText(node.element, kAXDescriptionAttribute) ?? node.identifier ?? node.role)
        var locator: Any = NSNull()
        if let identifier = node.identifier, !identifier.isEmpty,
           nodes.filter({ $0.role == node.role && $0.identifier == identifier }).count == 1 {
            locator = ["kind": "ax_identifier", "role": node.role, "name": identifier]
            addressable[try jsonKey(locator)] = node.element
        }
        var read: Any = NSNull()
        var value: Any = NSNull()
        if node.role == "AXStaticText", let text = try axText(node.element, kAXValueAttribute, limit: 4096) {
            read = "text"; value = text
        } else if capture.boolValue && ["AXTextField", "AXTextArea"].contains(node.role),
                  let text = try axText(node.element, kAXValueAttribute, limit: 4096) {
            read = "value"; value = text
        }
        controls.append(["id": "control_\(controls.count + 1)", "role": node.role,
                         "label": label.isEmpty ? node.role : label, "locator": locator,
                         "read": read, "value": value,
                         "enabled": try axBool(node.element, kAXEnabledAttribute) ?? false])
    }
    // Recheck process/bundle and selected window after the bounded capture.
    _ = try pinnedApplication(pin)
    let after = try elements(app, kAXWindowsAttribute as CFString, limit: 8)
    guard after.count == 1, CFEqual(after[0], window), try axText(window, kAXTitleAttribute) == title
    else { throw Refusal.windowChanged }
    return Capture(report: ["controls": controls, "omitted_private": privateCount,
                            "actions_executed": 0, "screenshots_captured": false],
                   controls: addressable, application: app, window: window)
}

func requireOwnedSimulation(_ pin: [String: Any]) throws {
    guard let bundle = pin["bundle"] as? [String: Any] else { throw Refusal.invalidRequest }
    let helper = try physicalPath(CommandLine.arguments[0])
    let directory = URL(fileURLWithPath: helper).deletingLastPathComponent().path
    let expected = try physicalPath(directory + "/AiralogyNativeReader.app")
    guard ownedSimulatorHash.count == 64, ownedSimulatorInfoHash.count == 64,
          bundle["bundle_path"] as? String == expected,
          bundle["bundle_id"] as? String == "org.airalogy.InstrumentInterfaceSimulator",
          bundle["executable_sha256"] as? String == ownedSimulatorHash,
          bundle["info_sha256"] as? String == ownedSimulatorInfoHash
    else { throw Refusal.simulationOnly }
    _ = try pinnedApplication(pin)
}

func simulationStep(_ request: [String: Any]) throws -> [String: Any] {
    try exact(request, ["operation", "snapshot", "expected", "step"])
    guard let selected = request["snapshot"] as? [String: Any],
          let pin = selected["pin"] as? [String: Any],
          let expected = request["expected"] as? [String: Any],
          let step = request["step"] as? [String: Any]
    else { throw Refusal.invalidRequest }
    try requireOwnedSimulation(pin)
    let operation = try string(step["operation"])
    try exact(step, operation == "fill" ? ["operation", "locator", "value"] : ["operation", "locator"])
    guard ["read", "fill", "click"].contains(operation),
          let locator = step["locator"] as? [String: Any]
    else { throw Refusal.invalidRequest }
    try exact(locator, ["kind", "role", "name"])
    guard locator["kind"] as? String == "ax_identifier" else { throw Refusal.invalidRequest }
    let role = try string(locator["role"])
    let name = try string(locator["name"])
    let before = try capture(selected)
    guard try sameJSON(before.report, expected) else { throw Refusal.staleObservation }
    guard let control = before.controls[try jsonKey(locator)],
          try axText(control, kAXRoleAttribute) == role,
          try axText(control, kAXIdentifierAttribute) == name
    else { throw Refusal.controlChanged }
    if operation != "read" {
        // Never activate or steal focus. An operator owns the selected GUI session.
        guard try axBool(before.application, kAXFrontmostAttribute) == true,
              let focused = try attribute(before.application, kAXFocusedWindowAttribute as CFString),
              CFGetTypeID(focused) == AXUIElementGetTypeID(),
              CFEqual(focused, before.window)
        else { throw Refusal.focusChanged }
        guard try axBool(control, kAXEnabledAttribute) == true else { throw Refusal.controlChanged }
    }
    if operation == "fill" {
        guard ["AXTextField", "AXTextArea"].contains(role),
              selected["capture_values"] as? Bool == true
        else { throw Refusal.invalidRequest }
        let value = try string(step["value"], limit: 4096, empty: true)
        var settable: DarwinBoolean = false
        guard AXUIElementIsAttributeSettable(control, kAXValueAttribute as CFString, &settable) == .success,
              settable.boolValue else { throw Refusal.controlChanged }
        guard AXUIElementSetAttributeValue(control, kAXValueAttribute as CFString, value as CFString) == .success
        else { throw Refusal.accessibilityFailure }
        guard try axText(control, kAXValueAttribute, limit: 4096) == value else { throw Refusal.controlChanged }
    } else if operation == "click" {
        guard role == "AXButton" else { throw Refusal.invalidRequest }
        var actions: CFArray?
        guard AXUIElementCopyActionNames(control, &actions) == .success,
              let actions = actions as? [String], actions.contains(kAXPressAction)
        else { throw Refusal.controlChanged }
        guard AXUIElementPerformAction(control, kAXPressAction as CFString) == .success
        else { throw Refusal.accessibilityFailure }
    }
    try requireOwnedSimulation(pin)
    let after = try capture(selected)
    guard CFEqual(before.window, after.window) else { throw Refusal.windowChanged }
    return ["snapshot": after.report, "operation_attempted": operation != "read", "hardware_qualified": false]
}

func handle(_ request: [String: Any]) throws -> [String: Any] {
    let operation = try string(request["operation"])
    switch operation {
    case "doctor":
        try exact(request, ["operation"])
        // Never set kAXTrustedCheckOptionPrompt or change system privacy settings.
        return ["schema": "airalogy.native-macos-doctor.v1", "accessibility_trusted": AXIsProcessTrusted(),
                "os_version": ProcessInfo.processInfo.operatingSystemVersionString,
                "helper_version": 2, "permissions_changed": false]
    case "inspect_bundle":
        try exact(request, ["operation", "bundle_path"])
        return try bundleIdentity(string(request["bundle_path"], limit: 4096))
    case "pin_process":
        try exact(request, ["operation", "bundle_path", "pid"])
        let bundle = try bundleIdentity(string(request["bundle_path"], limit: 4096))
        let pid = pid_t(try number(request["pid"], low: 1, high: Int(Int32.max)))
        return ["bundle": bundle, "process": try processIdentity(pid, bundle: bundle)]
    case "snapshot":
        return try capture(request).report
    case "simulation_step":
        return try simulationStep(request)
    default:
        throw Refusal.invalidRequest
    }
}

do {
    var data = Data()
    while let chunk = try FileHandle.standardInput.read(upToCount: 131_073 - data.count), !chunk.isEmpty {
        data.append(chunk)
        guard data.count <= 131_072 else { throw Refusal.boundExceeded }
    }
    guard data.count <= 131_072,
          let request = try JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { throw Refusal.invalidRequest }
    let result = try handle(request)
    let encoded = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    guard encoded.count <= 131_072 else { throw Refusal.boundExceeded }
    FileHandle.standardOutput.write(encoded)
    FileHandle.standardOutput.write(Data([10]))
} catch {
    let code = (error as? Refusal)?.rawValue ?? "native_transport_failure"
    // Never print OS error bodies, application content or private paths on failure.
    FileHandle.standardError.write(Data((code + "\n").utf8))
    exit(1)
}
