import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { ReactNode } from "react";
import { motionPresets } from "../lib/theme";
import LanguageSwitcher from "./LanguageSwitcher";

interface WizardShellProps {
  children: ReactNode;
  /** 1-based step index for the progress rail (omit to hide it). */
  step?: number;
  totalSteps?: number;
  /** Show a back chevron in the header. */
  onBack?: () => void;
  title?: string;
  subtitle?: string;
}

/**
 * Mobile-first screen wrapper for every wizard step: optional gradient surface,
 * a thin progress rail, a back affordance, and a centered content column.
 */
export default function WizardShell({
  children,
  step,
  totalSteps,
  onBack,
  title,
  subtitle,
}: WizardShellProps) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const showRail = typeof step === "number" && typeof totalSteps === "number";

  return (
    <div className="flex min-h-[100dvh] flex-col bg-canvas text-ink">
      <header className="mx-auto flex w-full max-w-2xl items-center gap-3 px-5 pt-6">
        <button
          type="button"
          onClick={() => (onBack ? onBack() : navigate(-1))}
          aria-label={t("common.back")}
          className="flex h-9 w-9 items-center justify-center rounded-pill bg-surfacestrong text-lg text-ink transition hover:bg-hairline"
        >
          ‹
        </button>
        {showRail && (
          <div className="flex flex-1 items-center gap-1.5" aria-hidden>
            {Array.from({ length: totalSteps! }).map((_, i) => (
              <span
                key={i}
                className={`h-1 flex-1 rounded-pill transition-colors ${
                  i < step! ? "bg-rausch" : "bg-hairline"
                }`}
              />
            ))}
          </div>
        )}
        <div className="ml-auto">
          <LanguageSwitcher />
        </div>
      </header>

      <motion.main
        initial={motionPresets.pageIn.initial}
        animate={motionPresets.pageIn.animate}
        transition={motionPresets.pageIn.transition}
        className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-5 pb-10 pt-6"
      >
        {title && <h1 className="text-display-lg font-bold text-ink">{title}</h1>}
        {subtitle && <p className="mt-2 text-base text-muted">{subtitle}</p>}
        <div className={title || subtitle ? "mt-6 flex flex-1 flex-col" : "flex flex-1 flex-col"}>
          {children}
        </div>
      </motion.main>
    </div>
  );
}
