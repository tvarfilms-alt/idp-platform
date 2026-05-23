import { firebaseConfig, VAPID_PUBLIC_KEY } from "./config.js";
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js";
import {
  getAuth, signInAnonymously, onAuthStateChanged,
} from "https://www.gstatic.com/firebasejs/10.12.5/firebase-auth.js";
import {
  getDatabase, ref, set, onValue, serverTimestamp,
} from "https://www.gstatic.com/firebasejs/10.12.5/firebase-database.js";

// ---------- constants & helpers ----------

const PALETTE = [
  "#4f8dfd", "#e0517a", "#9b59b6", "#16a085", "#e67e22", "#34495e",
  "#1abc9c", "#f368e0", "#5758bb", "#ff6b6b", "#2ecc71", "#ffc312",
];

const MOOD = {
  1: { color: "#e74c3c", emoji: "🔴", title: "Тяжёлый день" },
  2: { color: "#f5b62e", emoji: "🟡", title: "Так себе" },
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
};

const todayKey = () => {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
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
let ratings = [];     // [{uid,name,date,value}]
let members = [];     // [{uid,name,colorHex}]
let unsub = [];

function stopListeners() {
  unsub.forEach((fn) => { try { fn(); } catch (_) {} });
  unsub = [];
}

function startListeners(pairId) {
  stopListeners();

  unsub.push(onValue(ref(db, `pairs/${pairId}/ratings`), (snap) => {
    const val = snap.val() || {};
    ratings = Object.values(val);
    if (store.onboarded) renderMain();
  }, (e) => console.warn("ratings listener", e)));

  unsub.push(onValue(ref(db, `pairs/${pairId}/members`), (snap) => {
    const val = snap.val() || {};
    members = Object.values(val);
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
  const date = todayKey();
  await set(ref(db, `pairs/${store.pairId}/ratings/${date}_${uid}`), {
    uid, name: store.name, date, value, updatedAt: serverTimestamp(),
  });
}

const myToday = () => ratings.find((r) => r.uid === uid && r.date === todayKey());

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
  const hash = JSON.stringify({ r: ratings, m: members, n: notifHint() });
  const existing = $(".main");
  if (existing && hash === _lastMainHash) return;
  _lastMainHash = hash;

  const node = existing || mountTemplate("tpl-main");

  $("#btn-settings", node).onclick = renderSettings;

  const banner = $("#notif-banner", node);
  const hint = notifHint();
  if (hint) { banner.classList.remove("hidden"); banner.textContent = hint; }
  else banner.classList.add("hidden");

  const mine = myToday();
  const myStatus = $("#my-status", node);
  if (mine) {
    myStatus.textContent = `${MOOD[mine.value].emoji}  ${MOOD[mine.value].title}`;
    myStatus.style.color = MOOD[mine.value].color;
  } else {
    myStatus.textContent = "Ещё не оценён";
    myStatus.style.color = "";
  }

  node.querySelectorAll(".mood").forEach((btn) => {
    const value = Number(btn.dataset.value);
    btn.classList.toggle("chosen", mine && mine.value === value);
    btn.classList.toggle("dim", mine && mine.value !== value);
    btn.onclick = () => submitRating(value);
  });

  const partnersCard = $("#partners", node);
  const list = $("#partners-list", node);
  const others = members.filter((m) => m.uid !== uid);
  if (others.length) {
    partnersCard.classList.remove("hidden");
    list.innerHTML = "";
    others.forEach((m) => {
      const r = ratings.find((x) => x.uid === m.uid && x.date === todayKey());
      const row = document.createElement("div");
      row.className = "partner";
      const status = r
        ? `<span style="color:${MOOD[r.value].color}">${MOOD[r.value].emoji} ${MOOD[r.value].title}</span>`
        : `<span class="muted">ещё не оценил(а)</span>`;
      row.innerHTML = `<span class="dot" style="background:${m.colorHex}"></span>
        <span class="name">${escapeHtml(m.name)}</span> ${status}`;
      list.appendChild(row);
    });
  } else {
    partnersCard.classList.add("hidden");
  }

  renderChart($("#chart", node));
}

function renderSettings() {
  const node = mountTemplate("tpl-settings");
  $("#btn-back", node).onclick = () => { _lastMainHash = ""; renderMain(); };
  $("#set-name", node).textContent = store.name;
  $("#set-pair", node).textContent = store.pairId;

  const stateEl = $("#notif-state", node);
  const enableBtn = $("#btn-enable-notif", node);
  refreshNotifState(stateEl, enableBtn);

  enableBtn.onclick = async () => {
    enableBtn.disabled = true;
    enableBtn.textContent = "Подключаем…";
    try {
      await enableNotifications(false);
    } catch (e) {
      alert("Не удалось включить: " + (e.message || e));
    }
    enableBtn.disabled = false;
    enableBtn.textContent = "Включить напоминания";
    refreshNotifState(stateEl, enableBtn);
  };

  $("#btn-reset", node).onclick = () => {
    if (!confirm("Сбросить связь и имя на этом устройстве? Оценки в облаке сохранятся.")) return;
    stopListeners();
    store.onboarded = false;
    renderOnboarding();
  };
}

// ---------- chart (hand-drawn SVG) ----------

function renderChart(container) {
  const days = 14;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const dayList = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today); d.setDate(today.getDate() - i);
    dayList.push(d);
  }
  const keyOf = (d) => {
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${d.getFullYear()}-${m}-${day}`;
  };
  const dayKeys = dayList.map(keyOf);

  const recent = ratings.filter((r) => dayKeys.includes(r.date));
  if (!recent.length) {
    container.innerHTML = `<div class="chart-empty">Здесь появится график, как только вы начнёте оценивать дни.</div>`;
    return;
  }

  const people = [...new Set(recent.map((r) => r.uid))];
  const colorFor = (puid) => (members.find((m) => m.uid === puid)?.colorHex) || "#4f8dfd";
  const nameFor = (puid) => (members.find((m) => m.uid === puid)?.name) || puid.slice(0, 4);

  const W = 560, H = 240, padL = 34, padR = 14, padT = 16, padB = 28;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const xAt = (i) => padL + (dayList.length === 1 ? plotW / 2 : (plotW * i) / (dayList.length - 1));
  const yAt = (v) => padT + plotH - ((v - 1) / 2) * plotH;

  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">`;

  [1, 2, 3].forEach((v) => {
    const y = yAt(v);
    svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#2a2d36" stroke-width="1"/>`;
    svg += `<text x="6" y="${y + 5}" font-size="15">${MOOD[v].emoji}</text>`;
  });

  dayList.forEach((d, i) => {
    if (i % 3 !== 0 && i !== dayList.length - 1) return;
    const label = `${d.getDate()}.${String(d.getMonth() + 1).padStart(2, "0")}`;
    svg += `<text x="${xAt(i)}" y="${H - 8}" font-size="10" fill="#9aa0aa" text-anchor="middle">${label}</text>`;
  });

  people.forEach((puid) => {
    const pts = [];
    dayKeys.forEach((k, i) => {
      const r = recent.find((x) => x.uid === puid && x.date === k);
      if (r) pts.push({ x: xAt(i), y: yAt(r.value), v: r.value });
    });
    if (pts.length > 1) {
      const dAttr = pts.map((p, i) => (i ? "L" : "M") + p.x.toFixed(1) + " " + p.y.toFixed(1)).join(" ");
      svg += `<path d="${dAttr}" fill="none" stroke="${colorFor(puid)}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`;
    }
    pts.forEach((p) => {
      svg += `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="6" fill="${MOOD[p.v].color}" stroke="#0e0f13" stroke-width="2"/>`;
    });
  });

  svg += `</svg>`;

  const legend = people.map((puid) =>
    `<span class="item"><span class="dot" style="background:${colorFor(puid)}"></span>${escapeHtml(nameFor(puid))}</span>`
  ).join("");

  container.innerHTML = svg + `<div class="legend">${legend}</div>`;
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
  // Subscriptions live at a top-level node so the daily sender reads them all.
  await set(ref(db, `pushSubs/${uid}`), {
    uid, name: store.name,
    subscription: JSON.parse(JSON.stringify(sub)),
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
    try { await navigator.serviceWorker.register("sw.js"); } catch (e) { console.warn("sw", e); }
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
