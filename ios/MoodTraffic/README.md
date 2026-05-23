# Светофор настроения 🚦

iOS-приложение для двоих: каждый вечер приходит push «оцени день», вы жмёте
🔴 / 🟡 / 🟢, и оба видите график настроения друг друга в реальном времени.

- **Напоминание** — локальное уведомление в выбранное время, с кнопками
  оценки прямо в самом push (не нужно даже открывать приложение).
- **Синхронизация** — Firebase Firestore, real-time между двумя телефонами.
- **График** — нативный Swift Charts: по линии на каждого, точки окрашены по
  цвету дня, за последние 2 недели.

---

## Что нужно

- Mac с **Xcode 15+**
- iPhone у каждого из вас (iOS 16+)
- Бесплатный Apple ID (для запуска на своих устройствах платный Apple Developer
  не обязателен — только перeподписывать раз в 7 дней)
- Бесплатный аккаунт Google (для Firebase)

---

## Шаг 1. Создать проект Firebase

1. Зайдите на https://console.firebase.google.com и создайте проект (например
   `svetofor`). Google Analytics можно отключить.
2. Внутри проекта нажмите **Add app → iOS**.
   - **Bundle ID**: `com.svetofor.moodtraffic` (ровно так — он зашит в проекте).
3. Скачайте файл **`GoogleService-Info.plist`**.
4. Положите его в папку `Resources/` этого проекта и убедитесь, что имя ровно
   `GoogleService-Info.plist` (без `.example`).
5. В консоли Firebase включите:
   - **Build → Authentication → Sign-in method → Anonymous → Enable**
   - **Build → Firestore Database → Create database** (можно «production mode»).
6. Вкладка **Firestore → Rules**: вставьте содержимое файла
   [`firestore.rules`](./firestore.rules) и нажмите **Publish**.

---

## Шаг 2. Сгенерировать Xcode-проект

Проект описан как код в `project.yml` (через [XcodeGen](https://github.com/yonaskolb/XcodeGen)).

```bash
brew install xcodegen
cd ios/MoodTraffic
xcodegen generate
open MoodTraffic.xcodeproj
```

XcodeGen сам подтянет Firebase SDK через Swift Package Manager при первой сборке
(первый раз качается пару минут).

> Не хотите XcodeGen? Можно вручную: создать в Xcode новый App (SwiftUI, iOS 16),
> bundle id `com.svetofor.moodtraffic`, перетащить папки `Sources/` и
> `Resources/`, и добавить пакет `https://github.com/firebase/firebase-ios-sdk`
> (продукты **FirebaseAuth** и **FirebaseFirestore**). XcodeGen проще.

---

## Шаг 3. Запустить на телефоне

1. В Xcode выберите target **MoodTraffic** → вкладка **Signing & Capabilities**.
2. Поставьте свой **Apple ID** в *Team* (Xcode → Settings → Accounts, если ещё
   не добавлен). Bundle id при бесплатном аккаунте можно поменять на уникальный,
   например `com.вашеимя.moodtraffic` — тогда так же поменяйте его в
   `project.yml` и в Firebase.
3. Подключите iPhone кабелем, выберите его в списке устройств, нажмите ▶️.
4. На телефоне: **Настройки → Основные → VPN и управление устройством** →
   доверьте своему сертификату разработчика.
5. Повторите для второго телефона (того же или другого человека).

---

## Шаг 4. Связать вас двоих

1. На обоих телефонах при первом запуске:
   - введите своё имя,
   - выберите цвет (для графика),
   - введите **одинаковый код пары** (например `olya-sasha`).
2. Разрешите уведомления.
3. Готово — жмите цвет дня, и он сразу появляется у партнёра, а в нижней части
   экрана строится общий график.

---

## Про уведомления

Используются **локальные** уведомления — они работают без платного Apple
Developer и без сервера: телефон сам показывает напоминание в заданное время с
кнопками 🔴 🟡 🟢. Время меняется в ⚙️ Настройках.

> Если позже захотите «настоящие» серверные push (например, чтобы тыкать
> партнёра кнопкой) — это уже потребует Apple Developer Program ($99/год),
> APNs-ключа и Firebase Cloud Messaging. Архитектура к этому готова, скажите —
> добавлю.

---

## Структура

```
Sources/
  App/        — точка входа, AppDelegate (Firebase + обработка push-кнопок)
  Models/     — Rating, Member, MoodColor, утилиты дат, Color(hex:)
  Services/   — AuthService, FirebaseService (real-time), NotificationService
  State/      — AppState: настройки + связывание сервисов
  Views/      — Onboarding, Main (3 кнопки), MoodChart, Settings
Resources/    — Assets, сюда же кладётся GoogleService-Info.plist
firestore.rules — правила безопасности Firestore
project.yml   — описание проекта для XcodeGen
```
