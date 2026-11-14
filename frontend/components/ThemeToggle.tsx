"use client";

import { MoonIcon, SunIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

/** Light/dark switch. Follows the device setting until the visitor picks one; the choice is remembered. */
export default function ThemeToggle() {
  const [dark, setDark] = useState<boolean | null>(null);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  function toggle() {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("phoenix-theme", next ? "dark" : "light");
    } catch {}
    setDark(next);
  }

  return (
    <Button
      type="button" variant="outline" size="lg" onClick={toggle} aria-pressed={dark ?? false}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
    >
      {dark ? <SunIcon data-icon="inline-start" /> : <MoonIcon data-icon="inline-start" />}
      {/* Label only once we know the theme, so server and browser render the same HTML. */}
      {dark === null ? "Theme" : dark ? "Light mode" : "Dark mode"}
    </Button>
  );
}
