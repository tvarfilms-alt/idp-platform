// Sends each user their "rate your day" web-push at THEIR chosen local time.
// Run by .github/workflows/daily-push.yml every 15 minutes.
//
// Non-secret values are hardcoded below (public VAPID key, DB URL, subject —
// all already public via the web app). Only two SECRETS are read from env and
// must be set in repo Settings → Secrets and variables → Actions:
//   VAPID_PRIVATE_KEY         - matching private key for the public key below
//   FIREBASE_SERVICE_ACCOUNT  - full service-account JSON (one line)

const admin = require("firebase-admin");
const webpush = require("web-push");

// --- public (non-secret) config ---
const VAPID_PUBLIC_KEY = "BGBR-wgv7RAcMzbe1MwNdbwSeDGJXWCjNOdbwyGTXAQyFmdMNT7eZ1Z61scMy0yQzZh5XZD86EDW2-cxlNrXOX0";
const VAPID_SUBJECT = "https://tvarfilms-alt.github.io/idp-platform/";
const FIREBASE_DB_URL = "https://svetofor-51b8a-default-rtdb.europe-west1.firebasedatabase.app";

// --- secrets (from env) ---
const VAPID_PRIVATE_KEY = process.env.VAPID_PRIVATE_KEY;
const SERVICE_ACCOUNT_RAW = process.env.FIREBASE_SERVICE_ACCOUNT;

if (!VAPID_PRIVATE_KEY || !SERVICE_ACCOUNT_RAW) {
  console.log(
    "Секреты ещё не заданы (VAPID_PRIVATE_KEY / FIREBASE_SERVICE_ACCOUNT). " +
    "Добавь их в Settings → Secrets and variables → Actions. Пропускаю запуск."
  );
  process.exit(0); // graceful: no red failures until secrets exist
}

admin.initializeApp({
  credential: admin.credential.cert(JSON.parse(SERVICE_ACCOUNT_RAW)),
  databaseURL: FIREBASE_DB_URL,
});
const db = admin.database();

webpush.setVapidDetails(VAPID_SUBJECT, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY);

const payload = JSON.stringify({
  title: "Как прошёл день?",
  body: "Оцени сегодняшний день 🔴 🟡 🟢",
  url: ".",
});

// 30-min window with a 15-min cron survives an occasionally-skipped run.
const WINDOW_MIN = 30;

// Returns { mod, dateStr } = minutes-since-midnight and Y-M-D in the given tz.
function wallClock(tz) {
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz, hour12: false,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
  const p = Object.fromEntries(fmt.formatToParts(new Date()).map((x) => [x.type, x.value]));
  const hour = Number(p.hour) % 24;
  return { mod: hour * 60 + Number(p.minute), dateStr: `${p.year}-${p.month}-${p.day}` };
}

(async () => {
  const snap = await db.ref("pushSubs").once("value");
  const subs = snap.val() || {};
  let ok = 0, removed = 0, skipped = 0, failed = 0;

  for (const [key, rec] of Object.entries(subs)) {
    if (!rec || !rec.enabled || !rec.subscription || !rec.subscription.endpoint) { skipped++; continue; }

    const tz = rec.tz || "UTC";
    const hour = Number.isInteger(rec.hour) ? rec.hour : 21;
    const minute = Number.isInteger(rec.minute) ? rec.minute : 0;

    let now;
    try { now = wallClock(tz); }
    catch (_) { now = wallClock("UTC"); }

    const diff = now.mod - (hour * 60 + minute);
    if (!(diff >= 0 && diff < WINDOW_MIN)) { skipped++; continue; }
    if (rec.lastSent === now.dateStr) { skipped++; continue; }

    try {
      await webpush.sendNotification(rec.subscription, payload);
      await db.ref(`pushSubs/${key}/lastSent`).set(now.dateStr);
      ok++;
    } catch (err) {
      if (err.statusCode === 404 || err.statusCode === 410) {
        await db.ref(`pushSubs/${key}`).remove();
        removed++;
      } else {
        failed++;
        console.warn("send failed:", err.statusCode, err.body || err.message);
      }
    }
  }

  console.log(`done: sent=${ok} removed=${removed} skipped=${skipped} failed=${failed} total=${Object.keys(subs).length}`);
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });
