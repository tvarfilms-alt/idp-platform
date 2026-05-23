// Sends the daily "rate your day" web-push to every stored subscription.
// Run by .github/workflows/daily-push.yml on a schedule.
//
// Required env vars (set as GitHub Secrets):
//   FIREBASE_SERVICE_ACCOUNT  - full service-account JSON (one line)
//   FIREBASE_DB_URL           - Realtime Database URL (https://...firebasedatabase.app)
//   VAPID_PUBLIC_KEY          - same public key as docs/config.js
//   VAPID_PRIVATE_KEY         - matching private key (keep secret!)
//   VAPID_SUBJECT             - e.g. "mailto:you@example.com"

const admin = require("firebase-admin");
const webpush = require("web-push");

function requireEnv(name) {
  const v = process.env[name];
  if (!v) { console.error(`Missing env ${name}`); process.exit(1); }
  return v;
}

const serviceAccount = JSON.parse(requireEnv("FIREBASE_SERVICE_ACCOUNT"));
admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
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

(async () => {
  const snap = await db.ref("pushSubs").once("value");
  const subs = snap.val() || {};
  const entries = Object.entries(subs);
  let ok = 0, removed = 0, failed = 0;

  for (const [key, rec] of entries) {
    const sub = rec && rec.subscription;
    if (!sub || !sub.endpoint) continue;
    try {
      await webpush.sendNotification(sub, payload);
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

  console.log(`done: sent=${ok} removed=${removed} failed=${failed} total=${entries.length}`);
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });
