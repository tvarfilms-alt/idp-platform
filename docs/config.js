// ============================================================
//  FIREBASE — вставь сюда настройки своего проекта.
//  Замени ВЕСЬ блок ниже (от строки "const firebaseConfig = {"
//  до строки "};") на тот, что даёт Firebase по кнопке Copy
//  на экране регистрации Web-приложения.
//  Строку "export { ... }" в самом низу НЕ трогай.
// ============================================================
const firebaseConfig = {
  apiKey: "REPLACE_ME",
  authDomain: "REPLACE_ME.firebaseapp.com",
  projectId: "REPLACE_ME",
  storageBucket: "REPLACE_ME.appspot.com",
  messagingSenderId: "REPLACE_ME",
  appId: "REPLACE_ME",
};

// Публичный VAPID-ключ для web-push (МЕНЯТЬ НЕ НУЖНО).
const VAPID_PUBLIC_KEY =
  "BGBR-wgv7RAcMzbe1MwNdbwSeDGJXWCjNOdbwyGTXAQyFmdMNT7eZ1Z61scMy0yQzZh5XZD86EDW2-cxlNrXOX0";

export { firebaseConfig, VAPID_PUBLIC_KEY };
