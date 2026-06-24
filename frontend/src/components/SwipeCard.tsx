import { useState } from "react";
import {
  motion,
  useMotionValue,
  useTransform,
  type PanInfo,
} from "framer-motion";
import type { ReactNode } from "react";

interface SwipeCardProps {
  children: ReactNode;
  /** Fired when the card is flung far enough right (the "yes, talk to them" gesture). */
  onSwipeRight?: () => void;
  /** Fired when flung left (dismiss). */
  onSwipeLeft?: () => void;
  className?: string;
}

const THRESHOLD = 120;

/**
 * Full-bleed swipeable card — the signature interaction (spec §2). Drag horizontally;
 * past the threshold it commits and fires the matching callback. A LIKE/NOPE
 * stamp fades in as you drag, exactly like a dating app.
 */
export default function SwipeCard({
  children,
  onSwipeRight,
  onSwipeLeft,
  className = "",
}: SwipeCardProps) {
  const x = useMotionValue(0);
  const rotate = useTransform(x, [-220, 0, 220], [-14, 0, 14]);
  const likeOpacity = useTransform(x, [40, 160], [0, 1]);
  const nopeOpacity = useTransform(x, [-160, -40], [1, 0]);
  const [gone, setGone] = useState(false);

  function handleDragEnd(_: unknown, info: PanInfo) {
    if (info.offset.x > THRESHOLD) {
      setGone(true);
      onSwipeRight?.();
    } else if (info.offset.x < -THRESHOLD) {
      setGone(true);
      onSwipeLeft?.();
    }
  }

  return (
    <motion.div
      drag="x"
      dragConstraints={{ left: 0, right: 0 }}
      dragElastic={0.7}
      style={{ x, rotate }}
      onDragEnd={handleDragEnd}
      animate={gone ? { opacity: 0, scale: 0.9 } : { opacity: 1, scale: 1 }}
      whileTap={{ cursor: "grabbing" }}
      className={`relative cursor-grab touch-pan-y select-none ${className}`}
    >
      <motion.span
        style={{ opacity: likeOpacity }}
        className="pointer-events-none absolute left-5 top-5 z-10 -rotate-12 rounded-xl border-4 border-green-400 px-3 py-1 font-display text-2xl font-extrabold text-green-400"
      >
        LIKE
      </motion.span>
      <motion.span
        style={{ opacity: nopeOpacity }}
        className="pointer-events-none absolute right-5 top-5 z-10 rotate-12 rounded-xl border-4 border-white px-3 py-1 font-display text-2xl font-extrabold text-white"
      >
        NOPE
      </motion.span>
      {children}
    </motion.div>
  );
}
