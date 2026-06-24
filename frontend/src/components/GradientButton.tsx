import { motion, type HTMLMotionProps } from "framer-motion";

type Variant = "primary" | "ghost" | "ink";

interface GradientButtonProps extends HTMLMotionProps<"button"> {
  variant?: Variant;
  loading?: boolean;
  fullWidth?: boolean;
}

const VARIANT_CLASS: Record<Variant, string> = {
  primary: "pill-primary",
  ghost: "pill-ghost",
  ink: "pill-ink",
};

/** Round pill CTA — the signature button shape (spec §2). */
export default function GradientButton({
  children,
  variant = "ink",
  loading = false,
  fullWidth = false,
  disabled,
  className = "",
  ...rest
}: GradientButtonProps) {
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      className={`${VARIANT_CLASS[variant]} ${fullWidth ? "w-full" : ""} ${
        disabled || loading ? "opacity-60 cursor-not-allowed" : ""
      } ${className}`}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? (
        <span className="inline-flex items-center gap-2">
          <Spinner />
          <span>Hold on…</span>
        </span>
      ) : (
        children
      )}
    </motion.button>
  );
}

function Spinner() {
  return (
    <span
      aria-hidden
      className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
    />
  );
}
