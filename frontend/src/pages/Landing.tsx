import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import GradientButton from "../components/GradientButton";
import SwipeCard from "../components/SwipeCard";
import Avatar from "../components/Avatar";
import { microcopy } from "../lib/theme";
import { isAuthed } from "../api/client";

/**
 * Hero: the most characteristic thing in this product's world — a swipeable
 * dating-app card for your ex. Swipe right (or tap the CTA) to start the flow.
 */
export default function Landing() {
  const navigate = useNavigate();

  function start() {
    navigate(isAuthed() ? "/plan" : "/auth");
  }

  return (
    <div className="gradient-screen flex min-h-[100dvh] flex-col items-center justify-between px-6 py-10">
      <header className="flex w-full max-w-md items-center justify-between pt-2">
        <span className="font-display text-xl font-extrabold tracking-tight text-white">
          talk to your ex 💔
        </span>
        <button
          onClick={() => navigate("/auth")}
          className="text-sm font-semibold text-white/90 underline-offset-2 hover:underline"
        >
          {isAuthed() ? "Dashboard" : "Log in"}
        </button>
      </header>

      <main className="flex w-full max-w-md flex-1 flex-col items-center justify-center">
        <motion.h1
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center text-display-xl font-extrabold leading-[1.02] text-white"
        >
          {microcopy.tagline}
        </motion.h1>
        <p className="mt-3 max-w-xs text-center text-base text-white/90">
          Distill their voice from your old chats. Text them one more time — on your terms.
        </p>

        <div className="mt-9 w-full max-w-[20rem]">
          <SwipeCard onSwipeRight={start} onSwipeLeft={start}>
            <div className="rounded-card bg-white p-5 shadow-card">
              <div className="flex flex-col items-center">
                <Avatar name="Your ex" size={132} />
                <h2 className="mt-4 text-display-md font-bold text-ink">Your ex, 25</h2>
                <p className="mt-1 text-center text-sm text-muted">
                  Says they've changed. The data says otherwise.
                </p>
                <div className="mt-3 flex flex-wrap justify-center gap-2">
                  {["unread your texts", "left on read", "it's complicated"].map((t) => (
                    <span
                      key={t}
                      className="rounded-pill bg-tinder-start/[0.08] px-3 py-1 text-xs font-semibold text-tinder-start"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </SwipeCard>
          <p className="mt-3 text-center text-xs text-white/70">drag the card — or just tap below</p>
        </div>
      </main>

      <footer className="w-full max-w-md space-y-3 pb-2">
        <GradientButton variant="primary" fullWidth onClick={start}>
          Build their profile →
        </GradientButton>
        <p className="text-center text-xs text-white/70">
          Your data is encrypted and never leaves your box (except a one-time distillation).
        </p>
      </footer>
    </div>
  );
}
