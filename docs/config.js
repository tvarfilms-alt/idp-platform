// 1) Создай проект на https://console.firebase.google.com
// 2) Add app -> Web (</>), скопируй конфиг и вставь сюда вместо REPLACE_ME.
// 3) Включи Authentication -> Anonymous, и Firestore Database.
// Эти значения публичные (так и задумано у Firebase Web) — секретом является
// только service account для рассылки push (он хранится в GitHub Secrets).
export const firebaseConfig = {
  apiKey: "REPLACE_ME",
  authDomain: "REPLACE_ME.firebaseapp.com",
  projectId: "REPLACE_ME",
  storageBucket: "REPLACE_ME.appspot.com",
  messagingSenderId: "REPLACE_ME",
  appId: "REPLACE_ME",
};

// Публичный VAPID-ключ для web-push (сгенерирован заранее). Парный приватный
// ключ положи в GitHub Secrets как VAPID_PRIVATE_KEY — см. README.
export const VAPID_PUBLIC_KEY =
  "BGBR-wgv7RAcMzbe1MwNdbwSeDGJXWCjNOdbwyGTXAQyFmdMNT7eZ1Z61scMy0yQzZh5XZD86EDW2-cxlNrXOX0";
