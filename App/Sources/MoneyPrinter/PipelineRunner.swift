import AppKit
import Foundation

@Observable
class PipelineRunner {
    var isRunning = false
    var logs: [String] = []
    var outputPath: String?

    private var process: Process?
    private let projectRoot: String

    init() {
        if let root = ProcessInfo.processInfo.environment["MONEYPRINTER_ROOT"] {
            projectRoot = root
        } else {
            let url = URL(fileURLWithPath: #file)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .deletingLastPathComponent()
            projectRoot = url.path
        }
    }

    func runVeo(
        subject: String,
        language: String,
        fontSize: Int,
        resolution: String
    ) {
        var cmd = "cd \(shellEscape(projectRoot)) && uv run python Backend/cli.py veo"
        cmd += " \(shellEscape(subject))"
        cmd += " --language \(language)"
        cmd += " --font-size \(fontSize)"
        cmd += " --resolution \(resolution)"
        execute(cmd)
    }

    func runFinalize(
        videoPath: String,
        musicPath: String,
        scriptText: String,
        language: String,
        fontSize: Int,
        musicVolume: Double,
        crop: Bool
    ) {
        var cmd = "cd \(shellEscape(projectRoot)) && uv run python Backend/cli.py finalize"
        cmd += " --video \(shellEscape(videoPath))"
        if !musicPath.isEmpty {
            cmd += " --music \(shellEscape(musicPath))"
            cmd += " --music-volume \(String(format: "%.2f", musicVolume))"
        }
        if !scriptText.isEmpty {
            let tempScript = NSTemporaryDirectory() + "mp_script.txt"
            try? scriptText.write(toFile: tempScript, atomically: true, encoding: .utf8)
            cmd += " --script-file \(shellEscape(tempScript))"
        }
        cmd += " --language \(language)"
        cmd += " --font-size \(fontSize)"
        if !crop {
            cmd += " --no-crop"
        }
        execute(cmd)
    }

    func cancel() {
        process?.terminate()
    }

    func openOutputFolder() {
        let outputDir = projectRoot + "/output"
        NSWorkspace.shared.open(URL(fileURLWithPath: outputDir))
    }

    func openOutputFile() {
        guard let path = outputPath else { return }
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }

    // MARK: - Private

    private func execute(_ cmd: String) {
        guard !isRunning else { return }
        isRunning = true
        logs = []
        outputPath = nil

        let process = Process()
        self.process = process

        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-l", "-c", cmd]
        process.currentDirectoryURL = URL(fileURLWithPath: projectRoot)

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let line = String(data: data, encoding: .utf8) else { return }
            DispatchQueue.main.async {
                for l in line.components(separatedBy: .newlines) where !l.isEmpty {
                    self?.logs.append(l)
                    if l.contains("Output:") {
                        let parts = l.components(separatedBy: "Output: ")
                        if parts.count > 1 {
                            self?.outputPath = parts.last?.trimmingCharacters(in: .whitespaces)
                        }
                    }
                }
            }
        }

        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                self?.isRunning = false
                pipe.fileHandleForReading.readabilityHandler = nil
            }
        }

        do {
            try process.run()
        } catch {
            logs.append("Failed to start: \(error.localizedDescription)")
            isRunning = false
        }
    }

    private func shellEscape(_ s: String) -> String {
        "'" + s.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }
}
