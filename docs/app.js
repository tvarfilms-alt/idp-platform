import { firebaseConfig, VAPID_PUBLIC_KEY } from "./config.js";
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js";
import {
  getAuth, signInAnonymously, onAuthStateChanged,
} from "https://www.gstatic.com/firebasejs/10.12.5/firebase-auth.js";
import {
  getDatabase, ref, set, update, remove, onValue, serverTimestamp,
} from "https://www.gstatic.com/firebasejs/10.12.5/firebase-database.js";

// ---------- constants & helpers ----------

const PALETTE = [
  "#4f8dfd", "#e0517a", "#9b59b6", "#16a085", "#e67e22", "#34495e",
  "#1abc9c", "#f368e0", "#5758bb", "#ff6b6b", "#2ecc71", "#ffc312",
];

const MOOD = {
  1: { color: "#e74c3c", emoji: "🔴", title: "Тяжёлый день" },
  2: { color: "#f5b62e", emoji: "🟡", title: "Обычный" },
  3: { color: "#2ecc71", emoji: "🟢", title: "Хороший день" },
};

const store = {
  get pairId() { return localStorage.getItem("pairId") || ""; },
  set pairId(v) { localStorage.setItem("pairId", v); },
  get name() { return localStorage.getItem("name") || ""; },
  set name(v) { localStorage.setItem("name", v); },
  get colorHex() { return localStorage.getItem("colorHex") || PALETTE[0]; },
  set colorHex(v) { localStorage.setItem("colorHex", v); },
  get onboarded() { return localStorage.getItem("onboarded") === "1"; },
  set onboarded(v) { localStorage.setItem("onboarded", v ? "1" : "0"); },
  get notifHour() { return Number(localStorage.getItem("notifHour") ?? 21); },
  set notifHour(v) { localStorage.setItem("notifHour", String(v)); },
  get notifMinute() { return Number(localStorage.getItem("notifMinute") ?? 0); },
  set notifMinute(v) { localStorage.setItem("notifMinute", String(v)); },
};

const dayKeyOf = (d) => {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
};
const todayKey = () => dayKeyOf(new Date());
const localTz = () => {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; }
  catch (_) { return "UTC"; }
};

const $ = (sel, root = document) => root.querySelector(sel);

function mountTemplate(id) {
  const tpl = document.getElementById(id);
  const node = tpl.content.firstElementChild.cloneNode(true);
  const app = $("#app");
  app.innerHTML = "";
  app.appendChild(node);
  return node;
}

// ---------- app state ----------

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getDatabase(app);

let uid = null;
let ratings = [];
let members = [];
let unsub = [];

// UI state
let pending = null;       // selected-but-not-saved mood
let editing = false;      // re-voting an already saved day
let selectedDate = todayKey(); // which day we're rating (yyyy-mm-dd)
let chartDays = 7;        // preset range length
let customMode = false;
let chartFrom = null;     // Date (custom)
let chartTo = null;       // Date (custom)

function stopListeners() {
  unsub.forEach((fn) => { try { fn(); } catch (_) {} });
  unsub = [];
}

function startListeners(pairId) {
  stopListeners();
  unsub.push(onValue(ref(db, `pairs/${pairId}/ratings`), (snap) => {
    ratings = Object.values(snap.val() || {});
    if (store.onboarded) renderMain();
  }, (e) => console.warn("ratings listener", e)));
  unsub.push(onValue(ref(db, `pairs/${pairId}/members`), (snap) => {
    members = Object.values(snap.val() || {});
    if (store.onboarded) renderMain();
  }, (e) => console.warn("members listener", e)));
}

async function upsertMember() {
  if (!uid || !store.pairId) return;
  await set(ref(db, `pairs/${store.pairId}/members/${uid}`), {
    uid, name: store.name, colorHex: store.colorHex, joinedAt: serverTimestamp(),
  });
}

async function submitRating(value) {
  if (!uid || !store.pairId) return;
  const date = selectedDate;
  await set(ref(db, `pairs/${store.pairId}/ratings/${date}_${uid}`), {
    uid, name: store.name, date, value, updatedAt: serverTimestamp(),
  });
}

async function deleteMember(memberUid) {
  if (!store.pairId) return;
  const base = `pairs/${store.pairId}`;
  // remove all of that member's ratings, then the member node itself
  const theirs = ratings.filter((r) => r.uid === memberUid);
  await Promise.all(theirs.map((r) =>
    remove(ref(db, `${base}/ratings/${r.date}_${memberUid}`))));
  await remove(ref(db, `${base}/members/${memberUid}`));
  if (memberUid === uid) await remove(ref(db, `pushSubs/${uid}`)).catch(() => {});
}

const ratingFor = (u, date) => ratings.find((r) => r.uid === u && r.date === date);
const mySelected = () => ratingFor(uid, selectedDate);

function pluralDays(n) {
  const a = Math.abs(n) % 100, b = n % 10;
  if (a > 10 && a < 20) return "дней";
  if (b === 1) return "день";
  if (b >= 2 && b <= 4) return "дня";
  return "дней";
}

// Consecutive days (ending today) where I have a rating; if today isn't rated
// yet, the streak counts up to yesterday so it isn't reset to 0 prematurely.
function myStreak() {
  if (!uid) return 0;
  let count = 0, guard = 0;
  const d = new Date(); d.setHours(0, 0, 0, 0);
  if (!ratingFor(uid, dayKeyOf(d))) d.setDate(d.getDate() - 1);
  while (ratingFor(uid, dayKeyOf(d)) && guard < 3000) { count++; d.setDate(d.getDate() - 1); guard++; }
  return count;
}

function renderSummary(el) {
  const ordered = [...members].sort((a, b) => (a.uid === uid ? -1 : b.uid === uid ? 1 : 0));
  el.innerHTML = ordered.map((m) => {
    const r = ratingFor(m.uid, selectedDate);
    const moodColor = r ? MOOD[r.value].color : "#2a2e3a";
    const label = m.uid === uid ? "Ты" : escapeHtml(m.name || "—");
    const word = r ? MOOD[r.value].title : "нет оценки";
    return `<div class="sum-item">
      <div class="sum-circle" style="background:${moodColor};box-shadow:0 0 0 2px ${m.colorHex || "#4f8dfd"}"></div>
      <div class="sum-name">${label}</div>
      <div class="sum-word ${r ? "" : "muted"}">${word}</div>
    </div>`;
  }).join("");
}
const fmtShort = (dateStr) => {
  const [, m, d] = dateStr.split("-");
  return `${d}.${m}`;
};
const ruDate = (dateStr) => {
  const d = parseDateInput(dateStr);
  try { return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" }).format(d); }
  catch (_) { return fmtShort(dateStr); }
};
const shiftDate = (dateStr, days) => {
  const d = parseDateInput(dateStr);
  d.setDate(d.getDate() + days);
  return dayKeyOf(d);
};

// ---------- screens ----------

function renderOnboarding() {
  const node = mountTemplate("tpl-onboarding");
  const nameIn = $("#in-name", node);
  const pairIn = $("#in-pair", node);
  const startBtn = $("#btn-start", node);
  const colorRow = $("#color-row", node);

  let chosenColor = store.colorHex;
  PALETTE.forEach((hex) => {
    const sw = document.createElement("div");
    sw.className = "swatch" + (hex === chosenColor ? " selected" : "");
    sw.style.background = hex;
    sw.onclick = () => {
      chosenColor = hex;
      [...colorRow.children].forEach((c) => c.classList.remove("selected"));
      sw.classList.add("selected");
    };
    colorRow.appendChild(sw);
  });

  nameIn.value = store.name;
  pairIn.value = store.pairId;

  const validate = () => {
    startBtn.disabled = !nameIn.value.trim() || !pairIn.value.trim();
  };
  nameIn.oninput = validate;
  pairIn.oninput = validate;
  validate();

  startBtn.onclick = async () => {
    startBtn.disabled = true;
    startBtn.textContent = "Подождите…";
    store.name = nameIn.value.trim();
    store.colorHex = chosenColor;
    store.pairId = pairIn.value.trim().toLowerCase();
    await upsertMember();
    startListeners(store.pairId);
    store.onboarded = true;
    renderMain();
    enableNotifications(true).catch(() => {});
  };
}

let _lastMainHash = "";
function renderMain() {
  const hash = JSON.stringify({
    r: ratings, m: members, n: notifHint(), e: editing, p: pending, sd: selectedDate,
    cd: chartDays, cm: customMode,
    cf: chartFrom ? chartFrom.getTime() : 0, ct: chartTo ? chartTo.getTime() : 0,
  });
  const existing = $(".main");
  if (existing && hash === _lastMainHash) return;
  _lastMainHash = hash;

  const node = existing || mountTemplate("tpl-main");
  $("#btn-settings", node).onclick = renderSettings;

  const banner = $("#notif-banner", node);
  const hint = notifHint();
  if (hint) { banner.classList.remove("hidden"); banner.textContent = hint; }
  else banner.classList.add("hidden");

  // date selector
  const isToday = selectedDate === todayKey();
  const isYesterday = selectedDate === shiftDate(todayKey(), -1);
  const dateIn = $("#rate-date", node);
  dateIn.max = todayKey();
  dateIn.value = selectedDate;
  dateIn.onchange = () => {
    let v = dateIn.value || todayKey();
    if (v > todayKey()) v = todayKey();
    selectedDate = v; pending = null; editing = false;
    renderMain();
  };
  const goDate = (delta) => {
    const next = shiftDate(selectedDate, delta);
    if (next > todayKey()) return;
    selectedDate = next; pending = null; editing = false;
    renderMain();
  };
  $("#date-prev", node).onclick = () => goDate(-1);
  const nextBtn = $("#date-next", node);
  nextBtn.disabled = isToday;
  nextBtn.onclick = () => goDate(1);
  $("#date-label", node).textContent =
    isToday ? "Сегодня" : isYesterday ? "Вчера" : ruDate(selectedDate);
  $("#rate-q", node).textContent = isToday
    ? "Как прошёл твой день?"
    : "Как прошёл этот день?";

  const backToday = $("#back-today", node);
  backToday.classList.toggle("hidden", isToday);
  backToday.onclick = () => { selectedDate = todayKey(); pending = null; editing = false; renderMain(); };

  const streakEl = $("#streak", node);
  const s = myStreak();
  if (s > 0) { streakEl.classList.remove("hidden"); streakEl.textContent = `🔥 ${s} ${pluralDays(s)} подряд`; }
  else streakEl.classList.add("hidden");

  renderSummary($("#summary", node));

  const mine = mySelected();
  const locked = !!mine && !editing;

  node.querySelectorAll(".mood").forEach((btn) => {
    const value = Number(btn.dataset.value);
    const selected = locked ? mine.value === value : pending === value;
    const someChosen = locked ? true : pending !== null;
    btn.classList.toggle("chosen", selected);
    btn.classList.toggle("dim", someChosen && !selected);
    btn.disabled = locked;
    btn.onclick = () => {
      if (locked) return;
      pending = value;
      renderMain();
    };
  });

  const commitBtn = $("#btn-commit", node);
  const revoteBtn = $("#btn-revote", node);
  commitBtn.classList.toggle("hidden", locked || pending === null);
  revoteBtn.classList.toggle("hidden", !locked);
  commitBtn.onclick = async () => {
    if (pending === null) return;
    commitBtn.disabled = true;
    await submitRating(pending);
    pending = null; editing = false; commitBtn.disabled = false;
    renderMain();
  };
  revoteBtn.onclick = () => { editing = true; pending = mine.value; renderMain(); };

  // chart range chips
  node.querySelectorAll("#chart-range button").forEach((b) => {
    const isCustom = b.dataset.custom === "1";
    const active = isCustom ? customMode : (!customMode && chartDays === Number(b.dataset.days));
    b.classList.toggle("active", active);
    b.onclick = () => {
      if (isCustom) {
        customMode = true;
        if (!chartFrom || !chartTo) {
          chartTo = new Date(); chartTo.setHours(0, 0, 0, 0);
          chartFrom = new Date(chartTo); chartFrom.setDate(chartTo.getDate() - 29);
        }
      } else {
        customMode = false;
        chartDays = Number(b.dataset.days);
      }
      renderMain();
    };
  });

  const customBox = $("#custom-range", node);
  customBox.classList.toggle("hidden", !customMode);
  const fromIn = $("#range-from", node);
  const toIn = $("#range-to", node);
  if (customMode && chartFrom && chartTo) {
    fromIn.value = dayKeyOf(chartFrom);
    toIn.value = dayKeyOf(chartTo);
  }
  const onDate = () => {
    const f = parseDateInput(fromIn.value);
    const t = parseDateInput(toIn.value);
    if (f && t && f <= t) { chartFrom = f; chartTo = t; renderMain(); }
  };
  fromIn.onchange = onDate;
  toIn.onchange = onDate;

  renderChart($("#chart", node));
}

function renderSettings() {
  const node = mountTemplate("tpl-settings");
  $("#btn-back", node).onclick = () => { _lastMainHash = ""; renderMain(); };
  $("#set-name", node).textContent = store.name;
  $("#set-pair", node).textContent = store.pairId;

  // notification time
  const timeIn = $("#notif-time", node);
  timeIn.value = `${String(store.notifHour).padStart(2, "0")}:${String(store.notifMinute).padStart(2, "0")}`;
  timeIn.onchange = async () => {
    const [h, m] = timeIn.value.split(":").map(Number);
    if (Number.isInteger(h) && Number.isInteger(m)) {
      store.notifHour = h; store.notifMinute = m;
      await savePushPrefs();
    }
  };

  const stateEl = $("#notif-state", node);
  const enableBtn = $("#btn-enable-notif", node);
  refreshNotifState(stateEl, enableBtn);
  enableBtn.onclick = async () => {
    enableBtn.disabled = true;
    enableBtn.textContent = "Подключаем…";
    try { await enableNotifications(false); }
    catch (e) { alert("Не удалось включить: " + (e.message || e)); }
    enableBtn.disabled = false;
    enableBtn.textContent = "Включить напоминания";
    refreshNotifState(stateEl, enableBtn);
  };

  // my chart color
  const colorBox = $("#color-edit", node);
  colorBox.innerHTML = "";
  PALETTE.forEach((hex) => {
    const sw = document.createElement("div");
    sw.className = "swatch" + (hex === store.colorHex ? " selected" : "");
    sw.style.background = hex;
    sw.onclick = async () => {
      store.colorHex = hex;
      [...colorBox.children].forEach((c) => c.classList.remove("selected"));
      sw.classList.add("selected");
      if (uid && store.pairId) {
        await update(ref(db, `pairs/${store.pairId}/members/${uid}`), { colorHex: hex });
      }
    };
    colorBox.appendChild(sw);
  });

  // members admin
  const adminBox = $("#members-admin", node);
  adminBox.innerHTML = "";
  members.forEach((m) => {
    const row = document.createElement("div");
    row.className = "member-admin";
    const isMe = m.uid === uid;
    row.innerHTML = `<span class="dot" style="background:${m.colorHex}"></span>
      <span class="name">${escapeHtml(m.name)}</span>
      ${isMe ? '<span class="me-tag">это вы</span>' : ""}
      <button class="del" aria-label="Удалить">🗑️</button>`;
    row.querySelector(".del").onclick = async () => {
      const msg = isMe
        ? "Удалить себя из пары вместе со своими оценками? Приложение выйдет на этом устройстве."
        : `Удалить «${m.name}» и все его(её) оценки? Это нельзя отменить.`;
      if (!confirm(msg)) return;
      await deleteMember(m.uid);
      if (isMe) { stopListeners(); store.onboarded = false; renderOnboarding(); }
      else renderSettings();
    };
    adminBox.appendChild(row);
  });

  $("#btn-reset", node).onclick = () => {
    if (!confirm("Выйти на этом устройстве? Связь и имя сбросятся, но данные в облаке останутся.")) return;
    stopListeners();
    store.onboarded = false;
    renderOnboarding();
  };
}

// ---------- chart (hand-drawn SVG) ----------

function parseDateInput(v) {
  if (!v) return null;
  const [y, m, d] = v.split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

function buildDayList() {
  let start, end;
  if (customMode && chartFrom && chartTo) {
    start = new Date(chartFrom); end = new Date(chartTo);
  } else {
    end = new Date(); end.setHours(0, 0, 0, 0);
    start = new Date(end); start.setDate(end.getDate() - (chartDays - 1));
  }
  start.setHours(0, 0, 0, 0); end.setHours(0, 0, 0, 0);
  const list = [];
  const cur = new Date(start);
  let guard = 0;
  while (cur <= end && guard < 800) {
    list.push(new Date(cur));
    cur.setDate(cur.getDate() + 1);
    guard++;
  }
  return list;
}

function renderChart(container) {
  const dayList = buildDayList();
  const dayKeys = dayList.map(dayKeyOf);

  if (!members.length) {
    container.innerHTML = `<div class="chart-empty">Пока нет участников.</div>`;
    container.onclick = null;
    return;
  }

  const ordered = [...members].sort((a, b) =>
    a.uid === uid ? -1 : b.uid === uid ? 1 : 0);

  const n = dayList.length;
  const showWeekdays = n <= 14;
  const WD = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];

  const W = 560;
  const topPad = 6;
  const wkH = showWeekdays ? 16 : 0;
  const labelH = 18, rowH = 22, rowGap = 12, axisH = 20;
  const perMember = labelH + rowH + rowGap;
  const gridTop = topPad + wkH;
  const H = gridTop + ordered.length * perMember + axisH;

  const cellW = W / n;
  const g = cellW > 8 ? 2 : cellW > 4 ? 0.8 : 0.2;
  const rectW = Math.max(0.6, cellW - g);
  const rx = Math.min(4, Math.max(0, cellW / 3 - 0.4));
  const today = todayKey();

  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">`;

  // weekday labels (only for short ranges)
  if (showWeekdays) {
    dayList.forEach((d, i) => {
      svg += `<text x="${(i * cellW + cellW / 2).toFixed(1)}" y="${topPad + 11}" font-size="9" fill="#8b919e" text-anchor="middle">${WD[d.getDay()]}</text>`;
    });
  }

  ordered.forEach((m, k) => {
    const baseY = gridTop + k * perMember;
    const stripY = baseY + labelH;
    // row label: color dot + name
    svg += `<circle cx="7" cy="${baseY + 9}" r="5" fill="${m.colorHex || "#4f8dfd"}"/>`;
    svg += `<text x="18" y="${baseY + 13}" font-size="12" font-weight="600" fill="#f4f5f7">${escapeHtml(m.name || "—")}</text>`;
    dayKeys.forEach((key, i) => {
      const r = ratingFor(m.uid, key);
      const x = (i * cellW + g / 2).toFixed(2);
      const fill = r ? MOOD[r.value].color : "rgba(255,255,255,0.045)";
      svg += `<rect x="${x}" y="${stripY}" width="${rectW.toFixed(2)}" height="${rowH}" rx="${rx.toFixed(1)}" fill="${fill}"/>`;
    });
  });

  // bottom date axis
  const step = Math.max(1, Math.ceil(n / 6));
  dayList.forEach((d, i) => {
    if (i % step !== 0 && i !== n - 1) return;
    const label = `${d.getDate()}.${String(d.getMonth() + 1).padStart(2, "0")}`;
    svg += `<text x="${(i * cellW + cellW / 2).toFixed(1)}" y="${H - 6}" font-size="10" fill="#8b919e" text-anchor="middle">${label}</text>`;
  });

  // transparent per-day hit columns (tap a day to select it); outline today/selected
  const colTop = gridTop, colH = ordered.length * perMember;
  dayKeys.forEach((key, i) => {
    const x = (i * cellW).toFixed(2);
    let stroke = "none", sw = 0;
    if (key === selectedDate) { stroke = "#5b8cff"; sw = 1.5; }
    else if (key === today) { stroke = "#ffffff"; sw = 0.8; }
    svg += `<rect x="${x}" y="${colTop}" width="${cellW.toFixed(2)}" height="${colH}" fill="transparent" ` +
      `${sw ? `stroke="${stroke}" stroke-opacity="0.7" stroke-width="${sw}" rx="3"` : ""} data-date="${key}"/>`;
  });

  svg += `</svg>`;
  container.innerHTML = svg;

  container.onclick = (e) => {
    const el = e.target.closest && e.target.closest("[data-date]");
    if (!el) return;
    const d = el.getAttribute("data-date");
    if (d && d <= today) { selectedDate = d; pending = null; editing = false; renderMain(); }
  };
}

// ---------- notifications (web push) ----------

function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}
function isStandalone() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

function notifHint() {
  if (!pushSupported()) {
    if (!isStandalone()) {
      return "Чтобы включить push-напоминания: нажмите «Поделиться» → «На экран Домой», откройте приложение с домашнего экрана и включите уведомления в ⚙️.";
    }
    return "Это устройство/браузер не поддерживает web-push. Нужен iOS 16.4+ и установка на домашний экран.";
  }
  if (Notification.permission !== "granted") {
    return "Напоминания не включены. Откройте ⚙️ → «Включить напоминания».";
  }
  return "";
}

async function refreshNotifState(stateEl, enableBtn) {
  if (!pushSupported()) {
    stateEl.textContent = isStandalone()
      ? "web-push не поддерживается (нужен iOS 16.4+)."
      : "Сначала добавьте приложение на домашний экран и откройте его оттуда.";
    enableBtn.classList.add("hidden");
    return;
  }
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = reg ? await reg.pushManager.getSubscription() : null;
  if (Notification.permission === "granted" && sub) {
    stateEl.textContent = "✅ Напоминания включены на этом устройстве.";
    enableBtn.classList.add("hidden");
  } else {
    stateEl.textContent = "Напоминания пока выключены.";
    enableBtn.classList.remove("hidden");
  }
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

// Saves the user's reminder time/timezone (without changing the subscription).
async function savePushPrefs() {
  if (!uid) return;
  await update(ref(db, `pushSubs/${uid}`), {
    uid, name: store.name,
    hour: store.notifHour, minute: store.notifMinute, tz: localTz(),
    updatedAt: serverTimestamp(),
  });
}

async function enableNotifications(silent) {
  if (!pushSupported()) {
    if (!silent) throw new Error("web-push не поддерживается. Добавьте на домашний экран (iOS 16.4+).");
    return;
  }
  const perm = await Notification.requestPermission();
  if (perm !== "granted") {
    if (!silent) throw new Error("Разрешение на уведомления не выдано.");
    return;
  }
  const reg = await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
    });
  }
  await update(ref(db, `pushSubs/${uid}`), {
    uid, name: store.name,
    subscription: JSON.parse(JSON.stringify(sub)),
    enabled: true,
    hour: store.notifHour, minute: store.notifMinute, tz: localTz(),
    updatedAt: serverTimestamp(),
  });
  _lastMainHash = "";
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------- bootstrap ----------

async function main() {
  if ("serviceWorker" in navigator) {
    // Auto-reload once when a new version takes control, so updates always apply.
    let refreshing = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (refreshing) return;
      refreshing = true;
      location.reload();
    });
    try {
      const reg = await navigator.serviceWorker.register("sw.js");
      reg.update().catch(() => {});
    } catch (e) { console.warn("sw", e); }
  }

  onAuthStateChanged(auth, (user) => {
    if (!user) return;
    uid = user.uid;
    if (store.onboarded && store.pairId) {
      upsertMember();
      startListeners(store.pairId);
      renderMain();
    } else {
      renderOnboarding();
    }
  });

  try {
    await signInAnonymously(auth);
  } catch (e) {
    $("#app").innerHTML =
      `<div class="loading">Не удалось подключиться к Firebase.<br>Проверь config.js и что включён Anonymous Auth.<br><small>${escapeHtml(e.message || "")}</small></div>`;
  }
}

main();
