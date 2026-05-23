import Foundation
import SwiftUI

/// The three traffic-light moods. Raw values are stored in Firestore and used
/// as the Y axis of the chart (1 = worst … 3 = best).
enum MoodColor: Int, CaseIterable, Identifiable {
    case red = 1
    case yellow = 2
    case green = 3

    var id: Int { rawValue }

    var color: Color {
        switch self {
        case .red:    return Color(red: 0.90, green: 0.22, blue: 0.21)
        case .yellow: return Color(red: 0.98, green: 0.75, blue: 0.18)
        case .green:  return Color(red: 0.30, green: 0.69, blue: 0.31)
        }
    }

    var title: String {
        switch self {
        case .red:    return "Тяжёлый день"
        case .yellow: return "Так себе"
        case .green:  return "Хороший день"
        }
    }

    var emoji: String {
        switch self {
        case .red:    return "🔴"
        case .yellow: return "🟡"
        case .green:  return "🟢"
        }
    }
}

struct Rating: Identifiable, Equatable {
    let uid: String
    let name: String
    let date: String   // yyyy-MM-dd
    let value: Int     // 1...3
    let updatedAt: Date

    var id: String { "\(date)_\(uid)" }
    var mood: MoodColor { MoodColor(rawValue: value) ?? .yellow }
    var day: Date { DateUtils.date(fromKey: date) ?? Date() }
}

struct Member: Identifiable, Equatable {
    let uid: String
    let name: String
    let colorHex: String

    var id: String { uid }
    var color: Color { Color(hex: colorHex) ?? .blue }
}

enum DateUtils {
    static let keyFormatter: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    static func key(for date: Date) -> String { keyFormatter.string(from: date) }
    static func date(fromKey key: String) -> Date? { keyFormatter.date(from: key) }
    static var todayKey: String { key(for: Date()) }
}

extension Color {
    init?(hex: String) {
        var s = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.hasPrefix("#") { s.removeFirst() }
        guard s.count == 6, let v = Int(s, radix: 16) else { return nil }
        let r = Double((v >> 16) & 0xFF) / 255
        let g = Double((v >> 8) & 0xFF) / 255
        let b = Double(v & 0xFF) / 255
        self = Color(red: r, green: g, blue: b)
    }
}
