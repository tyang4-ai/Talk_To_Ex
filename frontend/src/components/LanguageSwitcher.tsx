import { useTranslation } from "react-i18next";
import { setLanguage } from "../i18n";

/** EN / 中 toggle for the portal (spec §26a). `light` for use on the gradient. */
export default function LanguageSwitcher({ light = false }: { light?: boolean }) {
  const { i18n } = useTranslation();
  const lng = i18n.language?.startsWith("zh") ? "zh" : "en";

  const base = "px-2 py-0.5 rounded-pill text-xs font-bold transition";
  const on = light ? "bg-white text-tinder-start" : "bg-ink text-white";
  const off = light ? "text-white/80 hover:text-white" : "text-muted hover:text-ink";

  return (
    <div className="flex items-center gap-1" role="group" aria-label="Language">
      <button
        type="button"
        onClick={() => setLanguage("en")}
        aria-pressed={lng === "en"}
        className={`${base} ${lng === "en" ? on : off}`}
      >
        EN
      </button>
      <button
        type="button"
        onClick={() => setLanguage("zh")}
        aria-pressed={lng === "zh"}
        className={`${base} ${lng === "zh" ? on : off}`}
      >
        中
      </button>
    </div>
  );
}
