import Foundation
import UserNotifications

enum RatingAction {
    static let category = "DAILY_RATING"
    static let red = "RATE_RED"
    static let yellow = "RATE_YELLOW"
    static let green = "RATE_GREEN"
}

@MainActor
final class NotificationService: ObservableObject {
    private let dailyId = "daily-rating"

    /// Adds the 🔴/🟡/🟢 buttons that appear on the reminder.
    func registerCategories() {
        let green = UNNotificationAction(identifier: RatingAction.green, title: "🟢 Хороший")
        let yellow = UNNotificationAction(identifier: RatingAction.yellow, title: "🟡 Так себе")
        let red = UNNotificationAction(identifier: RatingAction.red, title: "🔴 Тяжёлый")
        let category = UNNotificationCategory(
            identifier: RatingAction.category,
            actions: [green, yellow, red],
            intentIdentifiers: [],
            options: []
        )
        UNUserNotificationCenter.current().setNotificationCategories([category])
    }

    @discardableResult
    func requestAuthorization() async -> Bool {
        do {
            return try await UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .sound, .badge])
        } catch {
            return false
        }
    }

    /// Schedules a repeating daily reminder at the given local time.
    func scheduleDaily(hour: Int, minute: Int) {
        let center = UNUserNotificationCenter.current()
        center.removePendingNotificationRequests(withIdentifiers: [dailyId])

        let content = UNMutableNotificationContent()
        content.title = "Как прошёл день?"
        content.body = "Оцени сегодняшний день 🔴 🟡 🟢"
        content.sound = .default
        content.categoryIdentifier = RatingAction.category

        var components = DateComponents()
        components.hour = hour
        components.minute = minute

        let trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: true)
        let request = UNNotificationRequest(identifier: dailyId, content: content, trigger: trigger)
        center.add(request)
    }
}
