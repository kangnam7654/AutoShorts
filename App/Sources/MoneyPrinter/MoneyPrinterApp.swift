import SwiftUI

@main
struct MoneyPrinterApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 500, minHeight: 700)
        }
        .windowResizability(.contentSize)
    }
}
