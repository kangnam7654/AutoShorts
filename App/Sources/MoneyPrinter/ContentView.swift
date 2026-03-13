import SwiftUI

enum AppMode: String, CaseIterable {
    case veo = "Veo 생성"
    case finalize = "Finalize"
}

struct ContentView: View {
    @State private var runner = PipelineRunner()
    @State private var mode: AppMode = .veo

    // Veo mode
    @State private var subject = ""

    // Finalize mode
    @State private var videoPath = ""
    @State private var musicPath = ""
    @State private var scriptText = ""

    // Shared options
    @State private var language = "ko"
    @State private var fontSize = 55
    @State private var musicVolume = 0.10
    @State private var crop = true
    @State private var resolution = "720p"

    private let languages = [
        ("ko", "한국어"), ("en", "English"), ("ja", "日本語"), ("zh", "中文"),
        ("es", "Español"), ("fr", "Français"), ("de", "Deutsch"),
    ]

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("MoneyPrinter")
                    .font(.title2.bold())
                Spacer()
                Picker("", selection: $mode) {
                    ForEach(AppMode.allCases, id: \.self) { m in
                        Text(m.rawValue).tag(m)
                    }
                }
                .pickerStyle(.segmented)
                .frame(width: 200)
            }
            .padding()

            Divider()

            ScrollView {
                VStack(spacing: 16) {
                    if mode == .veo {
                        veoInputs
                    } else {
                        finalizeInputs
                    }

                    Divider()
                    optionsSection
                    Divider()
                    actionButtons
                    logSection
                    outputButtons
                }
                .padding()
            }
        }
        .frame(width: 500)
    }

    // MARK: - Veo Inputs

    private var veoInputs: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("영상 주제")
                .font(.callout)
                .foregroundStyle(.secondary)
            TextField("예: 사주로 알아보는 돈복", text: $subject)
                .textFieldStyle(.roundedBorder)
                .font(.body)
        }
    }

    // MARK: - Finalize Inputs

    private var finalizeInputs: some View {
        VStack(spacing: 16) {
            DropZone(
                label: "영상 파일을 드래그하거나 클릭",
                icon: "film",
                acceptedExtensions: ["mp4", "mov", "m4v", "avi", "mkv", "webm"],
                filePath: $videoPath
            )

            DropZone(
                label: "음악 파일 (선택)",
                icon: "music.note",
                acceptedExtensions: ["mp3", "wav", "m4a", "aac", "flac", "ogg"],
                filePath: $musicPath
            )

            VStack(alignment: .leading, spacing: 6) {
                Text("원본 스크립트 (선택 — 자막 검수용)")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                TextEditor(text: $scriptText)
                    .font(.body)
                    .frame(height: 80)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.gray.opacity(0.3))
                    )
            }
        }
    }

    // MARK: - Options

    private var optionsSection: some View {
        VStack(spacing: 12) {
            HStack {
                Text("언어")
                    .frame(width: 80, alignment: .leading)
                Picker("", selection: $language) {
                    ForEach(languages, id: \.0) { code, name in
                        Text(name).tag(code)
                    }
                }
                .labelsHidden()
            }

            HStack {
                Text("자막 크기")
                    .frame(width: 80, alignment: .leading)
                Picker("", selection: $fontSize) {
                    Text("작게 (40)").tag(40)
                    Text("보통 (55)").tag(55)
                    Text("크게 (80)").tag(80)
                    Text("매우 크게 (100)").tag(100)
                }
                .labelsHidden()
            }

            if mode == .veo {
                HStack {
                    Text("해상도")
                        .frame(width: 80, alignment: .leading)
                    Picker("", selection: $resolution) {
                        Text("720p").tag("720p")
                        Text("1080p").tag("1080p")
                        Text("4K").tag("4k")
                    }
                    .labelsHidden()
                }
            }

            if mode == .finalize {
                HStack {
                    Text("9:16 크롭")
                        .frame(width: 80, alignment: .leading)
                    Toggle("", isOn: $crop)
                        .labelsHidden()
                    Spacer()
                }

                if !musicPath.isEmpty {
                    HStack {
                        Text("음악 볼륨")
                            .frame(width: 80, alignment: .leading)
                        Slider(value: $musicVolume, in: 0.0...0.5, step: 0.05)
                        Text("\(Int(musicVolume * 100))%")
                            .frame(width: 36)
                            .monospacedDigit()
                    }
                }
            }
        }
    }

    // MARK: - Action Buttons

    private var actionButtons: some View {
        HStack(spacing: 12) {
            if runner.isRunning {
                Button("Cancel") {
                    runner.cancel()
                }
                .controlSize(.large)
            }

            Button {
                if mode == .veo {
                    runner.runVeo(
                        subject: subject,
                        language: language,
                        fontSize: fontSize,
                        resolution: resolution
                    )
                } else {
                    runner.runFinalize(
                        videoPath: videoPath,
                        musicPath: musicPath,
                        scriptText: scriptText,
                        language: language,
                        fontSize: fontSize,
                        musicVolume: musicVolume,
                        crop: crop
                    )
                }
            } label: {
                HStack {
                    if runner.isRunning {
                        ProgressView()
                            .controlSize(.small)
                        Text("Processing...")
                    } else {
                        Image(systemName: mode == .veo ? "wand.and.stars" : "play.fill")
                        Text(mode == .veo ? "Veo 생성" : "Finalize")
                    }
                }
                .frame(maxWidth: .infinity)
            }
            .controlSize(.large)
            .buttonStyle(.borderedProminent)
            .disabled(isActionDisabled || runner.isRunning)
        }
    }

    private var isActionDisabled: Bool {
        switch mode {
        case .veo: return subject.isEmpty
        case .finalize: return videoPath.isEmpty
        }
    }

    // MARK: - Log & Output

    private var logSection: some View {
        Group {
            if !runner.logs.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("Log")
                            .font(.callout.bold())
                        Spacer()
                    }
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 2) {
                                ForEach(Array(runner.logs.enumerated()), id: \.offset) { i, line in
                                    Text(stripAnsi(line))
                                        .font(.system(.caption, design: .monospaced))
                                        .foregroundStyle(logColor(line))
                                        .textSelection(.enabled)
                                        .id(i)
                                }
                            }
                            .padding(8)
                        }
                        .frame(height: 160)
                        .background(Color(nsColor: .textBackgroundColor))
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color.gray.opacity(0.3))
                        )
                        .onChange(of: runner.logs.count) {
                            withAnimation {
                                proxy.scrollTo(runner.logs.count - 1, anchor: .bottom)
                            }
                        }
                    }
                }
            }
        }
    }

    private var outputButtons: some View {
        Group {
            if runner.outputPath != nil && !runner.isRunning {
                HStack(spacing: 12) {
                    Button {
                        runner.openOutputFile()
                    } label: {
                        HStack {
                            Image(systemName: "play.rectangle")
                            Text("영상 열기")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .controlSize(.large)

                    Button {
                        runner.openOutputFolder()
                    } label: {
                        HStack {
                            Image(systemName: "folder")
                            Text("출력 폴더")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .controlSize(.large)
                }
            }
        }
    }

    private func stripAnsi(_ s: String) -> String {
        s.replacingOccurrences(
            of: "\\x1B\\[[0-9;]*[a-zA-Z]",
            with: "",
            options: .regularExpression
        )
    }

    private func logColor(_ line: String) -> Color {
        if line.contains("[OK]") || line.contains("success") || line.contains("Done") {
            return .green
        } else if line.contains("[ERR]") || line.contains("error") || line.contains("Failed") {
            return .red
        } else if line.contains("[WARN]") {
            return .orange
        }
        return .primary
    }
}
