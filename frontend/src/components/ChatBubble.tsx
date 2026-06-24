import { motion } from "framer-motion";
import { motionPresets } from "../lib/theme";

interface ChatBubbleProps {
  text: string;
  /** "in" = friend's outbound text (right, gradient); "out" = the ex's reply (left, grey). */
  side: "in" | "out";
  /** Show the animated typing dots instead of text. */
  typing?: boolean;
}

/**
 * Dating-app message-thread bubble (spec §2). The friend's own texts sit on the
 * right in the brand gradient; the ex's replies sit on the left in soft grey —
 * matching iMessage/Tinder thread conventions.
 */
export default function ChatBubble({ text, side, typing = false }: ChatBubbleProps) {
  const isFriend = side === "in";
  return (
    <motion.div
      initial={motionPresets.bubbleIn.initial}
      animate={motionPresets.bubbleIn.animate}
      transition={motionPresets.bubbleIn.transition}
      className={`flex w-full ${isFriend ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`max-w-[78%] rounded-3xl px-4 py-2.5 text-[15px] leading-snug shadow-sm ${
          isFriend
            ? "rounded-br-md bg-tinder-gradient-135 text-white"
            : "rounded-bl-md bg-black/[0.06] text-ink"
        }`}
      >
        {typing ? <TypingDots /> : text}
      </div>
    </motion.div>
  );
}

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-1" aria-label="typing">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="block h-2 w-2 rounded-full bg-current opacity-70"
          animate={{ y: [0, -3, 0] }}
          transition={{ duration: 0.7, repeat: Infinity, delay: i * 0.15 }}
        />
      ))}
    </span>
  );
}
