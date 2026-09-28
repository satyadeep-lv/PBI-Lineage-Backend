import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { cn } from "~/lib/utils";

type RevealState = "idle" | "armed" | "shown";

/**
 * Fades and lifts its content into place the first time it scrolls into view,
 * the way apple.com introduces each section. Styles live in app.css under
 * `[data-reveal]`: nothing is hidden until this effect has armed the element,
 * and reduced motion (or a browser without IntersectionObserver) shows it as-is.
 */
export function Reveal({
  children,
  className,
  delay = 0,
  variant = "rise",
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  /** Milliseconds to wait after entering view, for staggering siblings. */
  delay?: number;
  /** `zoom` also scales up from 94%, for large media such as the walkthrough. */
  variant?: "rise" | "zoom";
  as?: "div" | "section" | "article" | "li" | "figure";
}) {
  const ref = useRef<HTMLElement | null>(null);
  const [state, setState] = useState<RevealState>("idle");

  // A layout effect arms the element before the first paint, so content already on screen never flickers.
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element || typeof IntersectionObserver === "undefined") {
      setState("shown");
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setState("shown");
      return;
    }

    setState("armed");
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setState("shown");
          observer.disconnect();
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.12 },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <Tag
      ref={(node: HTMLElement | null) => {
        ref.current = node;
      }}
      data-reveal={state}
      data-reveal-variant={variant}
      className={cn(className)}
      style={delay ? ({ "--reveal-delay": `${delay}ms` } as CSSProperties) : undefined}
    >
      {children}
    </Tag>
  );
}
