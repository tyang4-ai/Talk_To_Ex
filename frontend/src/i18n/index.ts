/**
 * Portal internationalization (spec §26a) — Chinese / English.
 *
 * Synchronous, resource-inline i18next so `t()` returns real values on first
 * render (no Provider needed — components use the global instance). The chosen
 * language persists in localStorage. Translate copy incrementally: any key not
 * yet localized simply falls back to English.
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

const STORAGE_KEY = "ttx_lang";

export type Lang = "en" | "zh";

const en = {
  landing: {
    brand: "Ex.Change",
    tagline: "Swipe right on your ex 💔", // keep in sync with lib/theme microcopy
    subtitle:
      "Distill their voice from your old chats. Text them one more time — on your terms.",
    cta: "Build their profile →",
    login: "Log in",
    dashboard: "Dashboard",
  },
  common: { back: "Go back", tryAgain: "Try again", change: "Change" },
  model: {
    title: "Your ex will text on",
    auto: "Auto",
    autoHint: "Detected from your chats",
    qwen: "Qwen · best for Chinese",
    gemma: "Gemma · best for English",
  },
  building: {
    stages: [
      "Reading old messages",
      "Reliving the arguments",
      "Contemplating their wrongdoings",
      "Working up an apology",
      "Working up the nerve",
    ],
    contemplatingTitle: "{{name}} is contemplating their wrongdoings…",
    blurb: "This takes a moment.",
    closeHint: "Set it up and forget it — {{name}} will text you the moment they're ready.",
    texted: "💌 {{name}} texted you",
    textedBlurb: "Check your messages — they reached out first, in their own words.",
    fromNumber: "They'll text you from",
    toDashboard: "Go to dashboard",
    failed: "{{name}} got cold feet. Try again?",
    retry: "Build hit a snag. You can retry.",
    noPhone: "Add your phone number so they can reach you.",
    // legacy (sync flow)
    matchMade: "It's a match… sort of",
    doneBlurb: "Their voice is bottled and encrypted. Ready to meet them?",
    meet: "Meet them →",
  },
};

const zh = {
  landing: {
    brand: "Ex.Change",
    tagline: "向你的前任右滑 💔",
    subtitle: "从你们的旧聊天里提炼出 TA 的语气。再发一次消息——这次由你做主。",
    cta: "生成 TA 的档案 →",
    login: "登录",
    dashboard: "控制台",
  },
  common: { back: "返回", tryAgain: "再试一次", change: "更改" },
  model: {
    title: "你的前任将使用以下模型回复",
    auto: "自动",
    autoHint: "根据聊天记录检测",
    qwen: "Qwen · 中文最佳",
    gemma: "Gemma · 英文最佳",
  },
  building: {
    stages: [
      "正在重读旧消息",
      "正在重温那些争吵",
      "正在反省 TA 的过错",
      "正在酝酿一句道歉",
      "正在鼓起勇气",
    ],
    contemplatingTitle: "{{name}} 正在反省 TA 的过错……",
    blurb: "这需要一点时间。",
    closeHint: "设置好就放着 —— {{name}} 准备好了会主动给你发消息。",
    texted: "💌 {{name}} 给你发消息了",
    textedBlurb: "去看看你的短信吧 —— TA 主动联系了你，用 TA 自己的话。",
    fromNumber: "TA 会从这个号码联系你",
    toDashboard: "前往控制台",
    failed: "{{name}} 临阵退缩了，再试一次？",
    retry: "构建遇到点问题，可以重试。",
    noPhone: "添加你的手机号，TA 才能联系到你。",
    matchMade: "算是……配对成功了",
    doneBlurb: "TA 的语气已封装并加密。准备好见 TA 了吗？",
    meet: "去见 TA →",
  },
};

function stored(): Lang {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "zh" || v === "en") return v;
  } catch {
    /* no localStorage (SSR/tests) */
  }
  return "en";
}

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, zh: { translation: zh } },
  lng: stored(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  initImmediate: false, // synchronous → values available on first render
});

export function setLanguage(lng: Lang): void {
  void i18n.changeLanguage(lng);
  try {
    localStorage.setItem(STORAGE_KEY, lng);
  } catch {
    /* ignore */
  }
}

export default i18n;
