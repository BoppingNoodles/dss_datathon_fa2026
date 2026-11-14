"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

/** Light/dark switch. Follows the device setting until the visitor picks one; the choice is remembered. */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    const set = document.documentElement.dataset.theme as Theme | undefined;
    setTheme(set ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("phoenix-theme", next);
    } catch {}
    setTheme(next);
  }

  const dark = theme === "dark";
  return (
    <button
      type="button" onClick={toggle} aria-pressed={dark}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      className="inline-flex items-center gap-2 rounded-lg border border-line bg-card px-3 py-1.5 text-sm font-medium hover:border-brand"
    >
      <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        {dark ? (
          <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
          </>
        ) : (
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        )}
      </svg>
      {/* Label only once we know the theme, so server and browser render the same HTML. */}
      <span>{theme === null ? "Theme" : dark ? "Light mode" : "Dark mode"}</span>
    </button>
  );
}
