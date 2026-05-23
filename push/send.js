// Sends each user their "rate your day" web-push at THEIR chosen local time.
// Run by .github/workflows/daily-push.yml every 15 minutes; for each stored
// subscription it checks whether the user's reminder time (in their timezone)
// just passed, and sends once per day (deduped via lastSent).
//
// Required env vars (set as GitHub Secrets):
//   FIREBASE_SERVICE_ACCOUNT  - full service-account JSON (one line)
//   FIREBASE_DB_URL           - Realtime Database URL (https://...firebasedatabase.app)
//   VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT

const admin = require("firebase-admin");
const webpush = require("web-push");

function requireEnv(name) {
  const v = process.env[name];
  if (!v) { console.error(`Missing env ${name}`); process.exit(1); }
  return v;
}

admin.initializeApp({
  credential: admin.credential.cert(JSON.parse(requireEnv("FIREBASE_SERVICE_ACCOUNT"))),
  databaseURL: requireEnv("FIREBASE_DB_URL"),
});
const db = admin.database();

webpush.setVapidDetails(
  requireEnv("VAPID_SUBJECT"),
  requireEnv("VAPID_PUBLIC_KEY"),
  requireEnv("VAPID_PRIVATE_KEY")
);

const payload = JSON.stringify({
  title: "Как прошёл день?",
  body: "Оцени сегодняшний день 🔴 🟡 🟢",
  url: ".",
});

// How long after the target time we still consider a reminder "due".
// 30 min window with a 15-min cron survives an occasionally-skipped run.
const WINDOW_MIN = 30;

// Returns { mod, dateStr } = minutes-since-midnight and Y-M-D in the given tz.
function wallClock(tz) {
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz, hour12: false,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
  const p = Object.fromEntries(fmt.formatToParts(new Date()).map((x) => [x.type, x.value]));
  const hour = Number(p.hour) % 24; // guard against "24" at midnight
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
    const due = diff >= 0 && diff < WINDOW_MIN;
    if (!due) { skipped++; continue; }
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
