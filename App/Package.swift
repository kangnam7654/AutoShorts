// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MoneyPrinter",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "MoneyPrinter",
            path: "Sources/MoneyPrinter"
        ),
    ]
)
