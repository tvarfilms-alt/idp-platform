// ============================================================
//  FIREBASE — настройки твоего проекта уже вписаны.
//  Публичные значения (так и должно быть у Firebase Web).
// ============================================================
const firebaseConfig = {
  apiKey: "AIzaSyATFmO3x6gNeJkIBWFLEv_DLZfH9qyE1z4",
  authDomain: "svetofor-51b8a.firebaseapp.com",
  projectId: "svetofor-51b8a",
  storageBucket: "svetofor-51b8a.firebasestorage.app",
  messagingSenderId: "371619890934",
  appId: "1:371619890934:web:e0bd96a001be0a6f6b0ed7",
  measurementId: "G-YB96MK0BCE",
  // Адрес Realtime Database — впишется после её создания (см. README).
  databaseURL: "REPLACE_DB_URL",
};

// Публичный VAPID-ключ для web-push (МЕНЯТЬ НЕ НУЖНО).
const VAPID_PUBLIC_KEY =
  "BGBR-wgv7RAcMzbe1MwNdbwSeDGJXWCjNOdbwyGTXAQyFmdMNT7eZ1Z61scMy0yQzZh5XZD86EDW2-cxlNrXOX0";

export { firebaseConfig, VAPID_PUBLIC_KEY };
