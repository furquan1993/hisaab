import { useEffect, useId, useRef, useState, type ReactNode } from "react";

// Native auto popovers handle Escape, outside clicks, focus return and clipping:
// https://developer.mozilla.org/en-US/docs/Web/API/Popover_API/Using
export default function ColumnMenu({
  title,
  active,
  sorted,
  disabled,
  children,
}: {
  title: string;
  active?: boolean;
  sorted?: "ascending" | "descending";
  disabled?: boolean;
  children: ReactNode;
}) {
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [position, setPosition] = useState({ left: 0, top: 0, maxHeight: 420 });
  function placeMenu() {
    const rect = trigger.current?.getBoundingClientRect();
    if (!rect) return;
    const below = window.innerHeight - rect.bottom - 16;
    const above = rect.top - 16;
    const naturalHeight = panel.current?.offsetHeight || 320;
    const useBelow = below >= Math.min(naturalHeight, 420) || below >= above;
    const height = Math.min(420, Math.max(120, useBelow ? below : above));
    setPosition({
      left: Math.max(12, Math.min(rect.left, window.innerWidth - 292)),
      top: useBelow
        ? rect.bottom + 6
        : Math.max(12, rect.top - Math.min(naturalHeight, height) - 6),
      maxHeight: height,
    });
  }
  useEffect(() => {
    const reposition = (event: Event) => {
      if (event.target instanceof Node && panel.current?.contains(event.target))
        return;
      if (panel.current?.matches(":popover-open")) placeMenu();
    };
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, []);
  return (
    <>
      <button
        type="button"
        className={`column-trigger${active ? " is-filtered" : ""}`}
        aria-label={`${title}: filter and sort`}
        popoverTarget={id}
        disabled={disabled}
        ref={trigger}
        onClick={placeMenu}
      >
        <span>{title}</span>
        {sorted && (
          <span className="column-sort-indicator" aria-hidden="true">
            {sorted === "ascending" ? "↑" : "↓"}
          </span>
        )}
        <svg
          width="13"
          height="13"
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M2 3h12L9.5 8v4l-3 1V8L2 3Z"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinejoin="round"
          />
        </svg>
        {active && <span className="column-active-dot" aria-hidden="true" />}
      </button>
      <div
        id={id}
        popover="auto"
        ref={panel}
        className="column-menu"
        style={position}
        aria-label={`${title} options`}
      >
        <div className="column-menu-title">
          <strong>{title}</strong>
          <button
            type="button"
            popoverTarget={id}
            popoverTargetAction="hide"
            aria-label={`Close ${title} options`}
          >
            ×
          </button>
        </div>
        <fieldset className="column-menu-content" disabled={disabled}>
          {children}
        </fieldset>
      </div>
    </>
  );
}
