import SwiftUI
import Combine

/// Single source of truth for the UI: stores user settings (via @AppStorage),
/// owns the services and coordinates them. Re-publishes child changes so views
/// observing AppState update when ratings or auth change.
@MainActor
final class AppState: ObservableObject {
    @AppStorage("pairId") var pairId: String = ""
    @AppStorage("displayName") var displayName: String = ""
    @AppStorage("colorHex") var colorHex: String = "#4F8DFD"
    @AppStorage("notifHour") var notifHour: Int = 21
    @AppStorage("notifMinute") var notifMinute: Int = 0
    @AppStorage("onboarded") var onboarded: Bool = false

    let auth = AuthService()
    let firebase = FirebaseService()
    let notifications = NotificationService()

    private var cancellables = Set<AnyCancellable>()

    init() {
        auth.objectWillChange
            .sink { [weak self] in self?.objectWillChange.send() }
            .store(in: &cancellables)
        firebase.objectWillChange
            .sink { [weak self] in self?.objectWillChange.send() }
            .store(in: &cancellables)
    }

    var myUid: String? { auth.uid }

    func bootstrap() async {
        notifications.registerCategories()
        await auth.signInIfNeeded()
        if onboarded, !pairId.isEmpty {
            firebase.start(pairId: pairId)
        }
    }

    func completeOnboarding(pairId: String, name: String, colorHex: String) async {
        let cleanPair = pairId.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let cleanName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleanPair.isEmpty, !cleanName.isEmpty, let uid = auth.uid else { return }

        self.pairId = cleanPair
        self.displayName = cleanName
        self.colorHex = colorHex

        await firebase.upsertMember(pairId: cleanPair, uid: uid, name: cleanName, colorHex: colorHex)
        firebase.start(pairId: cleanPair)
        await notifications.requestAuthorization()
        notifications.scheduleDaily(hour: notifHour, minute: notifMinute)
        onboarded = true
    }

    func submit(_ mood: MoodColor) async {
        guard let uid = auth.uid, !pairId.isEmpty else { return }
        await firebase.setRating(pairId: pairId, uid: uid, name: displayName, value: mood.rawValue)
    }

    func rescheduleReminder() {
        notifications.scheduleDaily(hour: notifHour, minute: notifMinute)
    }

    func myTodayRating() -> Rating? {
        guard let uid = myUid else { return nil }
        return firebase.ratings.first { $0.uid == uid && $0.date == DateUtils.todayKey }
    }

    func reset() {
        firebase.stop()
        onboarded = false
    }
}
