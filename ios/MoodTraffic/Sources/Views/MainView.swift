import SwiftUI

struct MainView: View {
    @EnvironmentObject private var app: AppState
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 28) {
                    todayCard
                    ratingButtons
                    partnersToday
                    chartSection
                }
                .padding()
            }
            .navigationTitle("Сегодня")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showSettings = true } label: {
                        Image(systemName: "gearshape")
                    }
                }
            }
            .sheet(isPresented: $showSettings) {
                SettingsView()
            }
        }
    }

    // MARK: - Today

    private var todayCard: some View {
        VStack(spacing: 6) {
            Text("Как прошёл твой день?")
                .font(.title3).bold()
            if let mine = app.myTodayRating() {
                Text("\(mine.mood.emoji)  \(mine.mood.title)")
                    .font(.headline)
                    .foregroundStyle(mine.mood.color)
            } else {
                Text("Ещё не оценён")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 8)
    }

    private var ratingButtons: some View {
        VStack(spacing: 14) {
            ForEach([MoodColor.green, .yellow, .red]) { mood in
                Button {
                    Task { await app.submit(mood) }
                } label: {
                    HStack {
                        Text(mood.emoji).font(.title)
                        Text(mood.title)
                            .font(.title3).bold()
                        Spacer()
                        if app.myTodayRating()?.mood == mood {
                            Image(systemName: "checkmark.circle.fill")
                        }
                    }
                    .foregroundStyle(.white)
                    .padding()
                    .frame(maxWidth: .infinity)
                    .background(mood.color, in: RoundedRectangle(cornerRadius: 18))
                    .opacity(isSelected(mood) || app.myTodayRating() == nil ? 1 : 0.55)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func isSelected(_ mood: MoodColor) -> Bool {
        app.myTodayRating()?.mood == mood
    }

    // MARK: - Partner status

    private var partnersToday: some View {
        let others = app.firebase.members.filter { $0.uid != app.myUid }
        return Group {
            if !others.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Сегодня у вас")
                        .font(.headline)
                    ForEach(others) { member in
                        HStack {
                            Circle().fill(member.color).frame(width: 12, height: 12)
                            Text(member.name)
                            Spacer()
                            if let r = todayRating(for: member.uid) {
                                Text("\(r.mood.emoji) \(r.mood.title)")
                                    .foregroundStyle(r.mood.color)
                            } else {
                                Text("ещё не оценил(а)")
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 18))
            }
        }
    }

    private func todayRating(for uid: String) -> Rating? {
        app.firebase.ratings.first { $0.uid == uid && $0.date == DateUtils.todayKey }
    }

    // MARK: - Chart

    private var chartSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Последние 2 недели")
                .font(.headline)
            if app.firebase.ratings.isEmpty {
                Text("Здесь появится график, как только вы начнёте оценивать дни.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 120)
            } else {
                MoodChartView(ratings: app.firebase.ratings, members: app.firebase.members)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 18))
    }
}
