import Foundation
import FirebaseAuth

@MainActor
final class AuthService: ObservableObject {
    @Published private(set) var uid: String?

    func signInIfNeeded() async {
        if let user = Auth.auth().currentUser {
            uid = user.uid
            return
        }
        do {
            let result = try await Auth.auth().signInAnonymously()
            uid = result.user.uid
        } catch {
            print("Auth error: \(error.localizedDescription)")
        }
    }
}
