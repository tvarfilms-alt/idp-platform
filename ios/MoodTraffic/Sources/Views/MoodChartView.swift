import SwiftUI
import Charts

/// One line per person across the last 14 days; each dot is colored by that
/// day's traffic-light mood. Line colors follow each member's chosen color.
struct MoodChartView: View {
    let ratings: [Rating]
    let members: [Member]

    private var recent: [Rating] {
        let calendar = Calendar.current
        guard let cutoff = calendar.date(byAdding: .day, value: -13, to: calendar.startOfDay(for: Date()))
        else { return ratings }
        return ratings.filter { $0.day >= cutoff }
    }

    private func label(for rating: Rating) -> String {
        rating.name.isEmpty ? String(rating.uid.prefix(4)) : rating.name
    }

    var body: some View {
        Chart(recent) { rating in
            LineMark(
                x: .value("День", rating.day, unit: .day),
                y: .value("Настроение", rating.value),
                series: .value("Кто", label(for: rating))
            )
            .foregroundStyle(by: .value("Кто", label(for: rating)))
            .interpolationMethod(.monotone)

            PointMark(
                x: .value("День", rating.day, unit: .day),
                y: .value("Настроение", rating.value)
            )
            .foregroundStyle(rating.mood.color)
            .symbolSize(90)
        }
        .chartForegroundStyleScale(domain: seriesDomain, range: seriesColors)
        .chartYScale(domain: 0.5...3.5)
        .chartYAxis {
            AxisMarks(values: [1, 2, 3]) { value in
                AxisGridLine()
                AxisValueLabel {
                    if let i = value.as(Int.self), let mood = MoodColor(rawValue: i) {
                        Text(mood.emoji)
                    }
                }
            }
        }
        .chartXAxis {
            AxisMarks(values: .stride(by: .day, count: 3)) { _ in
                AxisGridLine()
                AxisValueLabel(format: .dateTime.day().month(.abbreviated))
            }
        }
        .frame(height: 240)
        .chartLegend(position: .bottom)
    }

    // Map series labels -> member colors so the two people are visually distinct.
    private var seriesDomain: [String] {
        let names = recent.map { label(for: $0) }
        return Array(Set(names)).sorted()
    }

    private var seriesColors: [Color] {
        seriesDomain.map { name in
            members.first { $0.name == name }?.color ?? .blue
        }
    }
}
