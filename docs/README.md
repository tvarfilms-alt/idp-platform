# Светофор настроения — веб-приложение (PWA) 🚦

Приложение для двоих, которое работает **полностью с телефона** (Mac не нужен):
открывается в Safari, добавляется на домашний экран как иконка, шлёт push
«оцени день» и показывает общий график настроения в реальном времени.

- **3 кнопки** 🔴 🟡 🟢 — оценка дня.
- **Синхронизация** — Firebase Realtime Database (real-time между телефонами).
- **График** — последние 2 недели, по линии на каждого.
- **Push** — настоящий, его рассылает раз в день GitHub Actions по расписанию.

Всё бесплатно. Все шаги ниже делаются **из браузера на телефоне**.

---

## Из чего состоит

```
docs/                      ← само веб-приложение (его раздаёт GitHub Pages)
  index.html app.js styles.css config.js sw.js manifest.webmanifest icons/
  database.rules.json      ← правила безопасности для Realtime Database
push/                      ← скрипт ежедневной рассылки push (Node + web-push)
.github/workflows/daily-push.yml  ← расписание (cron) рассылки
```

---

## Шаг 1. Firebase (≈5 минут)

1. Открой https://console.firebase.google.com → **Add project** (Analytics можно
   выключить).
2. Внутри проекта: значок **</> (Web)** → зарегистрируй веб-приложение → скопируй
   объект `firebaseConfig`.
3. Вставь свои значения в **`docs/config.js`** вместо `REPLACE_ME`
   (`apiKey`, `authDomain`, `projectId`, `storageBucket`, `messagingSenderId`,
   `appId`). Эти значения публичные — это нормально для Firebase Web.
4. **Authentication → Get started → Sign-in method → Anonymous → Enable.**
5. **Realtime Database → Create database** (регион любой, «locked mode»).
   Используем именно Realtime Database — она бесплатна без привязки карты.
6. Скопируй адрес базы (вида `https://…firebasedatabase.app`) и впиши его в
   `docs/config.js` в поле `databaseURL` вместо `REPLACE_DB_URL`.
7. Вкладка **Realtime Database → Rules**: вставь содержимое
   [`docs/database.rules.json`](./database.rules.json) и нажми **Publish**.

Файлы в репозитории правятся прямо в GitHub: открой файл → ✏️ (карандаш) →
Commit. Я уже создал ветку `claude/ios-daily-rating-app-6YGrj` — коммить в неё.

---

## Шаг 2. Секреты для рассылки push (в GitHub)

Открой репозиторий → **Settings → Secrets and variables → Actions → New
repository secret** и добавь 5 секретов:

| Имя | Значение |
|-----|----------|
| `VAPID_PUBLIC_KEY` | тот же ключ, что в `docs/config.js` (`BGBR-…`) |
| `VAPID_PRIVATE_KEY` | приватный VAPID-ключ (я дал его в чате; можно перегенерировать) |
| `VAPID_SUBJECT` | `mailto:tvarfilms@gmail.com` |
| `FIREBASE_DB_URL` | адрес Realtime Database (как в `databaseURL`) |
| `FIREBASE_SERVICE_ACCOUNT` | JSON сервис-аккаунта (см. ниже), вставить целиком |

**Где взять `FIREBASE_SERVICE_ACCOUNT`:** Firebase Console → ⚙️ **Project
settings → Service accounts → Generate new private key** → скачается JSON →
открой его, скопируй **весь** текст и вставь как значение секрета.

> Приватные ключи нигде не коммить — только в Secrets. В коде лежит лишь
> публичный VAPID-ключ, это безопасно.

---

## Шаг 3. Включить хостинг (GitHub Pages)

Репозиторий → **Settings → Pages**:
- **Source:** Deploy from a branch
- **Branch:** `claude/ios-daily-rating-app-6YGrj`, папка **`/docs`** → **Save**

Через минуту появится адрес вида
`https://tvarfilms-alt.github.io/idp-platform/`. Это и есть приложение.

---

## Шаг 4. Установить на телефон и включить уведомления

На **каждом** телефоне (у тебя и у жены):

1. Открой адрес из шага 3 в **Safari**.
2. Кнопка «Поделиться» → **«На экран Домой»**. Появится иконка-светофор.
3. Запусти приложение **с домашнего экрана** (это важно — web-push на iOS
   работает только так, нужен iOS **16.4+**).
4. Введи имя, выбери цвет и **одинаковый код пары** на обоих телефонах.
5. ⚙️ → **«Включить напоминания»** → разреши уведомления.

Готово: жмёшь цвет дня — он сразу виден партнёру, строится общий график.

---

## Шаг 5. Активировать ежедневный авто-push

⚠️ Особенность GitHub: задачи по расписанию (`cron`) запускаются **только из
ветки по умолчанию** (master). Пока workflow живёт лишь в feature-ветке, авто-
рассылка не сработает. Варианты:

- **Проверить прямо сейчас вручную:** репозиторий → **Actions → Daily mood push
  → Run workflow** (кнопка). Это разошлёт push немедленно — удобно для теста.
- **Включить расписание навсегда:** влей ветку `claude/ios-daily-rating-app-6YGrj`
  в `master` (Pull Request можно создать и смёрджить прямо с телефона в приложении
  GitHub). После этого cron заработает сам. Не забудь тогда переключить и Pages на
  `master` /docs.

---

## Изменить время напоминания

В файле `.github/workflows/daily-push.yml` строка `cron: "0 18 * * *"` —
это **18:00 UTC = 21:00 по Москве**. Формат: `минута час * * *` (час в UTC).
Например, 22:30 МСК → `30 19 * * *`. GitHub может присылать с задержкой
в несколько минут — это нормально для напоминания.

---

## Ограничения iOS (честно)

- Web-push на iPhone требует **iOS 16.4+** и **установки на домашний экран**.
- Уведомления приходят, только если приложение хоть раз открыли с домашнего
  экрана и выдали разрешение.
- Если хочется «железобетонной» доставки и кнопок-оценок прямо в уведомлении —
  это уже нативное приложение (нужен Mac + Xcode, опц. Apple Developer). Нативный
  Swift-вариант лежит в истории git, если однажды доберёшься до Mac.
