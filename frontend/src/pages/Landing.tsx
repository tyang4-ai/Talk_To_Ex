import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";
import GradientButton from "../components/GradientButton";
import SwipeCard from "../components/SwipeCard";
import Avatar from "../components/Avatar";
import LanguageSwitcher from "../components/LanguageSwitcher";
import { isAuthed } from "../api/client";

/**
 * Hero. On desktop it's a two-column layout — the pitch + CTA on the left, the
 * signature swipeable dating-app card on the right. It stacks (card first, then
 * the pitch) on narrow screens. Swipe right or tap the CTA to start.
 */
export default function Landing() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  function start() {
    navigate(isAuthed() ? "/plan" : "/auth");
  }

  return (
    <div className="flex min-h-[100dvh] flex-col bg-canvas px-6 py-8 text-ink">
      <header className="mx-auto flex w-full max-w-5xl items-center justify-between pt-2">
        <span className="font-display text-xl font-extrabold tracking-tight text-ink">
          {t("landing.brand")}
        </span>
        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          <button
            onClick={() => navigate("/auth")}
            className="text-sm font-semibold text-ink underline-offset-4 hover:underline"
          >
            {isAuthed() ? t("landing.dashboard") : t("landing.login")}
          </button>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col items-center justify-center gap-10 py-10 md:flex-row-reverse md:gap-16">
        {/* Swipe card (DOM-first → renders on the right on desktop) */}
        <div className="w-full max-w-[20rem] shrink-0">
          <SwipeCard onSwipeRight={start} onSwipeLeft={start}>
            <div className="rounded-card border border-hairline bg-white p-6 shadow-card">
              <div className="flex flex-col items-center">
                <Avatar name="Your ex" size={128} />
                <h2 className="mt-4 font-display text-display-md font-semibold text-ink">
                  Your ex, 25
                </h2>
                <p className="mt-1 text-center text-sm italic text-muted">
                  Says they've changed. The data says otherwise.
                </p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {["unread your texts", "left on read", "it's complicated"].map((tag) => (
                    <span
                      key={tag}
                      className="rounded-pill border border-rausch/30 px-3 py-1 text-xs font-semibold text-rausch"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </SwipeCard>
          <p className="mt-3 text-center text-xs text-muted">drag the card — or just tap below</p>
        </div>

        {/* Pitch + CTA (renders on the left on desktop) */}
        <div className="flex max-w-md flex-col items-center text-center md:items-start md:text-left">
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="text-display-xl font-extrabold leading-[1.05] text-ink"
          >
            {t("landing.tagline")}
          </motion.h1>
          <p className="mt-4 max-w-sm text-base text-body">{t("landing.subtitle")}</p>
          <div className="mt-8 w-full max-w-xs">
            <GradientButton variant="primary" fullWidth onClick={start}>
              {t("landing.cta")}
            </GradientButton>
            <p className="mt-3 text-xs text-muted">
              Your data is encrypted and never leaves your box (except a one-time distillation).
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
