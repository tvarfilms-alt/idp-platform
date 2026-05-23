import SwiftUI

struct RootView: View {
    @EnvironmentObject private var app: AppState

    var body: some View {
        if app.onboarded {
            MainView()
        } else {
            OnboardingView()
        }
    }
}
