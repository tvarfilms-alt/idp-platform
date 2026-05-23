import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject private var app: AppState

    @State private var name = ""
    @State private var pairCode = ""
    @State private var colorHex = ColorPalette.options.first!
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Светофор настроения")
                        .font(.title2).bold()
                    Text("Каждый вечер оценивайте свой день 🔴 🟡 🟢 и видьте настроение друг друга в реальном времени.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Section("Как вас зовут") {
                    TextField("Имя", text: $name)
                        .textInputAutocapitalization(.words)
                }

                Section("Цвет на графике") {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 6), spacing: 12) {
                        ForEach(ColorPalette.options, id: \.self) { hex in
                            Circle()
                                .fill(Color(hex: hex) ?? .blue)
                                .frame(height: 34)
                                .overlay {
                                    if hex == colorHex {
                                        Image(systemName: "checkmark")
                                            .font(.caption.bold())
                                            .foregroundStyle(.white)
                                    }
                                }
                                .onTapGesture { colorHex = hex }
                        }
                    }
                    .padding(.vertical, 4)
                }

                Section("Код пары") {
                    TextField("например: olya-sasha", text: $pairCode)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Text("Придумайте общий код и введите одинаковый на обоих телефонах — так приложение свяжет вас.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section {
                    Button {
                        Task {
                            saving = true
                            await app.completeOnboarding(pairId: pairCode, name: name, colorHex: colorHex)
                            saving = false
                        }
                    } label: {
                        HStack {
                            Spacer()
                            if saving { ProgressView() } else { Text("Начать").bold() }
                            Spacer()
                        }
                    }
                    .disabled(!canSubmit || saving)
                }
            }
            .navigationTitle("Добро пожаловать")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private var canSubmit: Bool {
        !name.trimmingCharacters(in: .whitespaces).isEmpty &&
        !pairCode.trimmingCharacters(in: .whitespaces).isEmpty
    }
}

enum ColorPalette {
    static let options = [
        "#4F8DFD", "#E0517A", "#9B59B6", "#16A085",
        "#E67E22", "#34495E", "#1ABC9C", "#F368E0",
        "#5758BB", "#FF6B6B", "#2ECC71", "#FFC312"
    ]
}
