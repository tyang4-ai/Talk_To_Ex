interface TagPickerProps {
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  max?: number;
}

/** Multi-select personality tags rendered as toggleable pills (Intake page). */
export default function TagPicker({ options, selected, onChange, max }: TagPickerProps) {
  function toggle(tag: string) {
    if (selected.includes(tag)) {
      onChange(selected.filter((t) => t !== tag));
    } else {
      if (max && selected.length >= max) return;
      onChange([...selected, tag]);
    }
  }

  return (
    <div className="flex flex-wrap gap-2">
      {options.map((tag) => {
        const active = selected.includes(tag);
        return (
          <button
            type="button"
            key={tag}
            onClick={() => toggle(tag)}
            aria-pressed={active}
            className={`rounded-pill border px-4 py-2 text-sm font-semibold transition ${
              active
                ? "border-transparent bg-rausch text-white"
                : "border-hairline bg-white text-ink hover:border-ink"
            }`}
          >
            {tag}
          </button>
        );
      })}
    </div>
  );
}
