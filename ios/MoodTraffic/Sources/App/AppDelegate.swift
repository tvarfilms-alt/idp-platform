import UIKit
import UserNotifications
import FirebaseCore
import FirebaseAuth
import FirebaseFirestore

/// Configures Firebase on launch and handles taps on the daily notification —
/// including the 🔴/🟡/🟢 action buttons, which write a rating even when the
/// app is in the background.
final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        if FirebaseApp.app() == nil {
            if Bundle.main.path(forResource: "GoogleService-Info", ofType: "plist") != nil {
                FirebaseApp.configure()
            } else {
                print("⚠️ GoogleService-Info.plist не найден. Добавь его в проект — см. README.md")
            }
        }
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    // Show the reminder even when the app is open.
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .sound]
    }

    // Handle the quick-rate action buttons.
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                didReceive response: UNNotificationResponse) async {
        let value: Int
        switch response.actionIdentifier {
        case RatingAction.red:    value = MoodColor.red.rawValue
        case RatingAction.yellow: value = MoodColor.yellow.rawValue
        case RatingAction.green:  value = MoodColor.green.rawValue
        default: return // a plain tap just opens the app
        }

        let defaults = UserDefaults.standard
        let pairId = defaults.string(forKey: "pairId") ?? ""
        let name = defaults.string(forKey: "displayName") ?? ""
        guard !pairId.isEmpty, FirebaseApp.app() != nil else { return }

        if Auth.auth().currentUser == nil {
            _ = try? await Auth.auth().signInAnonymously()
        }
        guard let uid = Auth.auth().currentUser?.uid else { return }

        let docId = "\(DateUtils.todayKey)_\(uid)"
        let ref = Firestore.firestore()
            .collection("pairs").document(pairId)
            .collection("ratings").document(docId)
        try? await ref.setData([
            "uid": uid,
            "name": name,
            "date": DateUtils.todayKey,
            "value": value,
            "updatedAt": FieldValue.serverTimestamp()
        ], merge: true)
    }
}
