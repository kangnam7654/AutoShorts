import SwiftUI
import UniformTypeIdentifiers

struct DropZone: View {
    let label: String
    let icon: String
    let acceptedExtensions: Set<String>
    @Binding var filePath: String
    @State private var isTargeted = false

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 10)
                .strokeBorder(
                    isTargeted ? Color.accentColor : Color.gray.opacity(0.4),
                    style: StrokeStyle(lineWidth: 2, dash: filePath.isEmpty ? [8] : [])
                )
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(isTargeted ? Color.accentColor.opacity(0.1) : Color.clear)
                )

            if filePath.isEmpty {
                VStack(spacing: 6) {
                    Image(systemName: icon)
                        .font(.title2)
                        .foregroundStyle(.secondary)
                    Text(label)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            } else {
                HStack {
                    Image(systemName: icon)
                        .foregroundStyle(.green)
                    Text(URL(fileURLWithPath: filePath).lastPathComponent)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Spacer()
                    Button {
                        filePath = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 12)
            }
        }
        .frame(height: 60)
        .onDrop(of: [.fileURL], isTargeted: $isTargeted) { providers in
            guard let provider = providers.first else { return false }
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { data, _ in
                guard let data = data as? Data,
                      let url = URL(dataRepresentation: data, relativeTo: nil, isAbsolute: true)
                else { return }
                let ext = url.pathExtension.lowercased()
                guard acceptedExtensions.contains(ext) else { return }
                DispatchQueue.main.async {
                    filePath = url.path
                }
            }
            return true
        }
        .onTapGesture {
            let panel = NSOpenPanel()
            panel.allowsMultipleSelection = false
            panel.canChooseDirectories = false
            if panel.runModal() == .OK, let url = panel.url {
                filePath = url.path
            }
        }
    }
}
