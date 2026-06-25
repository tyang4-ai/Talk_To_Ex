import type { GuideStep } from "../components/StepGuide";

export interface PlatformGuide {
  id:
    | "instagram"
    | "facebook"
    | "whatsapp"
    | "iphone"
    | "wechat"
    | "android"
    | "discord"
    | "telegram"
    | "email"
    | "other";
  platform: string;
  emoji: string;
  steps: GuideStep[];
  note?: string;
  accept: string;
  hint: string;
}

/** Per-platform export walkthroughs, verbatim from spec §10.1. */
export const importGuides: PlatformGuide[] = [
  {
    id: "instagram",
    platform: "Instagram",
    emoji: "📸",
    accept: ".zip,.json",
    hint: "Upload the .zip (or the message_*.json files)",
    steps: [
      { title: "Open Settings → Accounts Center" },
      { title: "Go to Your information and permissions" },
      {
        title: "Tap Download your information",
        detail: "Request the export in JSON format — choose Messages only.",
      },
      {
        title: "Wait for the email, then download the .zip",
        detail: "Instagram emails a link when the export is ready (minutes to a day).",
      },
      { title: "Upload the .zip below", detail: "We auto-detect the format and find your chat." },
    ],
    note: "Exports are newest-first and paginated — we sort and stitch them back together for you.",
  },
  {
    id: "whatsapp",
    platform: "WhatsApp",
    emoji: "💬",
    accept: ".txt,.zip",
    hint: "Upload the exported _chat.txt",
    steps: [
      { title: "Open the chat with your ex" },
      { title: "Tap ⋯ (or their name) → Export chat" },
      {
        title: "Choose Without media",
        detail: "Media isn't needed — just the messages keep it small.",
      },
      {
        title: "Send the .txt to yourself",
        detail: "AirDrop, email, or save to Files, then open it on this device.",
      },
      { title: "Upload the _chat.txt below" },
    ],
    note: "On a Chinese phone? If you see 上午/下午 timestamps, re-export with the phone language set to English or 24-hour time for the cleanest parse.",
  },
  {
    id: "iphone",
    platform: "iPhone (iMessage & SMS)",
    emoji: "📱",
    accept: ".db,.txt",
    hint: "Upload sms.db (or a 3uTools/iMazing text export)",
    steps: [
      {
        title: "Set Messages → Keep Messages = Forever",
        detail: "Settings → Messages → Keep Messages. Do this before backing up.",
      },
      {
        title: "Make an unencrypted backup",
        detail: "Use the Apple Devices app on Windows — uncheck Encrypt local backup.",
      },
      {
        title: "Find sms.db in the backup",
        detail: "The wizard's help link shows exactly where it lands on your PC.",
      },
      { title: "Upload sms.db below", detail: "Or upload a text export from 3uTools / iMazing." },
    ],
    note: "We read your messages locally and decode the modern iOS format properly — Chinese text stays intact.",
  },
  {
    id: "wechat",
    platform: "WeChat",
    emoji: "🟢",
    accept: ".txt,.csv,.html",
    hint: "Upload a .txt/.csv/.html export — or paste below",
    steps: [
      {
        title: "Run the bundled local-decrypt helper",
        detail: "On a PC where you're logged into WeChat, it produces a .txt of your chat.",
      },
      { title: "Upload the .txt below" },
      {
        title: "No helper? Paste instead",
        detail: "Open the chat, copy the messages, and paste them in the box below.",
      },
    ],
    note: "WeChat is best-effort — the plaintext paste fallback always works, so you're never stuck.",
  },
  {
    id: "android",
    platform: "Android (SMS & MMS)",
    emoji: "🤖",
    accept: ".xml,.csv",
    hint: "Upload the SMS Backup & Restore .xml",
    steps: [
      {
        title: 'Install "SMS Backup & Restore"',
        detail: "It's free on the Play Store (by SyncTech).",
      },
      {
        title: "Tap Set up a backup → Messages",
        detail: "You can include just your ex's conversation, or everything.",
      },
      {
        title: "Back up to a local file",
        detail: "Choose phone storage; it writes an .xml file.",
      },
      { title: "Upload the .xml below" },
    ],
    note: "Backup type 1 = received, type 2 = sent — we map who-said-what automatically.",
  },
  {
    id: "facebook",
    platform: "Facebook / Messenger",
    emoji: "🟦",
    accept: ".zip,.json",
    hint: "Upload the Messenger .zip (or message_*.json)",
    steps: [
      { title: "Open Settings & privacy → Accounts Center" },
      { title: "Go to Your information and permissions → Download your information" },
      {
        title: "Request the export — Messages, JSON format",
        detail: "Pick Messages only and Format: JSON (not HTML) for the cleanest parse.",
      },
      {
        title: "Wait for the email, then download the .zip",
        detail: "Meta emails a link when it's ready (minutes to a day).",
      },
      { title: "Upload the .zip below" },
    ],
    note: "Messenger uses the same Meta export as Instagram — we stitch the paginated files and repair garbled accents for you.",
  },
  {
    id: "discord",
    platform: "Discord",
    emoji: "🎮",
    accept: ".json,.csv",
    hint: "Upload a DiscordChatExporter .json",
    steps: [
      {
        title: "Get DiscordChatExporter",
        detail: "It's a free, open-source tool — Discord's own data download only includes YOUR messages, not theirs.",
      },
      { title: "Export the DM with your ex", detail: "Choose Format: JSON." },
      { title: "Upload the .json below", detail: "It has both sides of the conversation." },
    ],
    note: "Both sides of the DM come through — we tell who's who from the message authors.",
  },
  {
    id: "telegram",
    platform: "Telegram",
    emoji: "✈️",
    accept: ".json",
    hint: "Upload Telegram's result.json",
    steps: [
      { title: "Open Telegram Desktop", detail: "The export lives in the desktop app, not mobile." },
      { title: "Open the chat → ⋯ → Export chat history" },
      {
        title: "Choose JSON, uncheck media",
        detail: "Machine-readable JSON gives the cleanest result; media isn't needed.",
      },
      { title: "Upload result.json below" },
    ],
    note: "We read Telegram's formatted-text messages (bold, links, etc.) as plain text.",
  },
  {
    id: "email",
    platform: "Email",
    emoji: "✉️",
    accept: ".mbox,.eml",
    hint: "Upload a .mbox (or a single .eml)",
    steps: [
      {
        title: "Gmail: use Google Takeout",
        detail: "takeout.google.com → Mail → export. You'll get a .mbox file.",
      },
      {
        title: "Or save individual emails as .eml",
        detail: "Most desktop mail apps let you drag an email out as a .eml file.",
      },
      { title: "Upload the .mbox or .eml below" },
    ],
    note: "Great for capturing how they wrote to you in longer form. We strip quoted replies and signatures.",
  },
  {
    id: "other",
    platform: "Anything else",
    emoji: "🗂️",
    accept: ".txt,.csv,.json,.zip,.html,.pdf",
    hint: "Upload any text/CSV/JSON export — or paste below",
    steps: [
      {
        title: "Export your chat however you can",
        detail: "Most apps (Signal, Line, Slack, Kakao, Snapchat, …) can export or copy to text, CSV, or JSON.",
      },
      { title: "Upload the file below", detail: "Our generic reader handles common date/sender/message layouts." },
      {
        title: "Nothing exports cleanly? Paste it",
        detail: "Open the chat, copy the messages, and paste them in the box below — that always works.",
      },
    ],
    note: "When in doubt, this is the catch-all. If we can't auto-detect it, the plaintext paste never fails.",
  },
];

/**
 * Add your OWN annotated screenshots (spec §27 — never forum-lifted) by setting
 * `image` on any step above, e.g. `{ title: "...", image: "/guides/whatsapp-export.png" }`,
 * and dropping the file in `frontend/public/guides/`. StepGuide renders it inline.
 */
