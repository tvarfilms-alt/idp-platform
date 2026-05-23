import Foundation
import FirebaseFirestore

/// Real-time bridge to Firestore. Holds the latest ratings and members for the
/// current pair and keeps them live via snapshot listeners.
///
/// Not @MainActor on purpose: Firestore delivers snapshot callbacks on the main
/// thread, so @Published mutations here are already main-thread, and keeping the
/// type non-isolated avoids actor-isolation errors in the escaping listeners.
final class FirebaseService: ObservableObject {
    @Published private(set) var ratings: [Rating] = []
    @Published private(set) var members: [Member] = []

    private let db = Firestore.firestore()
    private var ratingsListener: ListenerRegistration?
    private var membersListener: ListenerRegistration?

    private func pairRef(_ pairId: String) -> DocumentReference {
        db.collection("pairs").document(pairId)
    }

    func start(pairId: String) {
        stop()
        let base = pairRef(pairId)

        ratingsListener = base.collection("ratings")
            .order(by: "date")
            .addSnapshotListener { [weak self] snapshot, error in
                if let error { print("ratings listener: \(error.localizedDescription)") }
                guard let docs = snapshot?.documents else { return }
                self?.ratings = docs.compactMap { Self.rating(from: $0.data()) }
            }

        membersListener = base.collection("members")
            .addSnapshotListener { [weak self] snapshot, error in
                if let error { print("members listener: \(error.localizedDescription)") }
                guard let docs = snapshot?.documents else { return }
                self?.members = docs.compactMap { Self.member(from: $0.data()) }
            }
    }

    func stop() {
        ratingsListener?.remove(); ratingsListener = nil
        membersListener?.remove(); membersListener = nil
        ratings = []
        members = []
    }

    func upsertMember(pairId: String, uid: String, name: String, colorHex: String) async {
        let ref = pairRef(pairId).collection("members").document(uid)
        do {
            try await ref.setData([
                "uid": uid,
                "name": name,
                "colorHex": colorHex,
                "joinedAt": FieldValue.serverTimestamp()
            ], merge: true)
        } catch {
            print("upsertMember: \(error.localizedDescription)")
        }
    }

    func setRating(pairId: String, uid: String, name: String, value: Int,
                   date: String = DateUtils.todayKey) async {
        let ref = pairRef(pairId).collection("ratings").document("\(date)_\(uid)")
        do {
            try await ref.setData([
                "uid": uid,
                "name": name,
                "date": date,
                "value": value,
                "updatedAt": FieldValue.serverTimestamp()
            ], merge: true)
        } catch {
            print("setRating: \(error.localizedDescription)")
        }
    }

    static func rating(from data: [String: Any]) -> Rating? {
        guard let uid = data["uid"] as? String,
              let date = data["date"] as? String,
              let value = data["value"] as? Int else { return nil }
        let name = data["name"] as? String ?? ""
        let updatedAt = (data["updatedAt"] as? Timestamp)?.dateValue() ?? Date()
        return Rating(uid: uid, name: name, date: date, value: value, updatedAt: updatedAt)
    }

    static func member(from data: [String: Any]) -> Member? {
        guard let uid = data["uid"] as? String else { return nil }
        let name = data["name"] as? String ?? "—"
        let colorHex = data["colorHex"] as? String ?? "#4F8DFD"
        return Member(uid: uid, name: name, colorHex: colorHex)
    }
}
