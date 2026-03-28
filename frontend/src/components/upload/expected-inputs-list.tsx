import { cn } from "@/lib/utils";

interface ExpectedInputsListProps {
  items: readonly string[];
  /** Visually de-emphasized label above the list */
  label?: string;
  className?: string;
}

/** Lightweight, scannable bullet list for template “expected inputs”. */
export function ExpectedInputsList({
  items,
  label = "Recommended files",
  className,
}: ExpectedInputsListProps) {
  if (items.length === 0) return null;
  return (
    <div className={cn(className)}>
      {label ? (
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground/90">
          {label}
        </p>
      ) : null}
      <ul
        className={cn(
          "mt-2 space-y-1 m-0 p-0 list-none",
          label ? "" : "mt-0"
        )}
      >
        {items.map((item) => (
          <li
            key={item}
            className="flex gap-2 text-xs text-foreground/90 leading-snug pl-0"
          >
            <span
              className="text-muted-foreground/80 shrink-0 w-3 text-center select-none"
              aria-hidden
            >
              ·
            </span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
