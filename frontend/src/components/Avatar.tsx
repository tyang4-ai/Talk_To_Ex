interface AvatarProps {
  name: string;
  src?: string | null;
  size?: number; // px
  className?: string;
}

/** Large rounded avatar (spec §2). Falls back to the ex's initial on the gradient. */
export default function Avatar({ name, src, size = 96, className = "" }: AvatarProps) {
  const initial = (name?.trim()?.[0] ?? "?").toUpperCase();
  return (
    <div
      className={`relative shrink-0 overflow-hidden rounded-avatar bg-tinder-gradient-135 shadow-card ring-4 ring-white/70 ${className}`}
      style={{ width: size, height: size }}
    >
      {src ? (
        <img src={src} alt={name} className="h-full w-full object-cover" />
      ) : (
        <span
          className="flex h-full w-full items-center justify-center font-display font-extrabold text-white"
          style={{ fontSize: size * 0.42 }}
          aria-hidden
        >
          {initial}
        </span>
      )}
    </div>
  );
}
