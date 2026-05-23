import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var app: AppState
    @Environment(\.dismiss) private var dismiss

    @State private var reminderTime = Date()
    @State private var confirmReset = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Напоминание") {
                    DatePicker("Время каждый день",
                               selection: $reminderTime,
                               displayedComponents: .hourAndMinute)
                        .onChange(of: reminderTime) { newValue in
                            let comps = Calendar.current.dateComponents([.hour, .minute], from: newValue)
                            app.notifHour = comps.hour ?? 21
                            app.notifMinute = comps.minute ?? 0
                            app.rescheduleReminder()
                        }
                    Text("Push придёт в это время с кнопками 🔴 🟡 🟢 — оценить день можно прямо из уведомления.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Профиль") {
                    LabeledContent("Имя", value: app.displayName)
                    LabeledContent("Код пары") {
                        Text(app.pairId).foregroundStyle(.secondary)
                    }
                }

                Section {
                    Button("Сбросить и выйти", role: .destructive) {
                        confirmReset = true
                    }
                }
            }
            .navigationTitle("Настройки")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Готово") { dismiss() }
                }
            }
            .onAppear {
                var comps = DateComponents()
                comps.hour = app.notifHour
                comps.minute = app.notifMinute
                reminderTime = Calendar.current.date(from: comps) ?? Date()
            }
            .alert("Сбросить настройки?", isPresented: $confirmReset) {
                Button("Отмена", role: .cancel) {}
                Button("Сбросить", role: .destructive) {
                    app.reset()
                    dismiss()
                }
            } message: {
                Text("Связь с парой и имя будут сброшены на этом устройстве. Оценки в облаке сохранятся.")
            }
        }
    }
}
