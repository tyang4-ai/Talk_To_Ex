import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { motionPresets } from "../lib/theme";

interface CardProps {
  children: ReactNode;
  className?: string;
  /** Disable the entrance animation (e.g. for static dashboard tiles). */
  still?: boolean;
}

/** White rounded card on the soft neutral surface — the primary content vessel. */
export default function Card({ children, className = "", still = false }: CardProps) {
  if (still) {
    return (
      <div className={`rounded-card bg-card p-6 shadow-soft ${className}`}>{children}</div>
    );
  }
  return (
    <motion.div
      initial={motionPresets.cardIn.initial}
      animate={motionPresets.cardIn.animate}
      transition={motionPresets.cardIn.transition}
      className={`rounded-card bg-card p-6 shadow-soft ${className}`}
    >
      {children}
    </motion.div>
  );
}
