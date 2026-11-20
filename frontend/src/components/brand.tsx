"use client";

import { useTheme } from "../app/theme-provider";
import Image from "next/image";

export function Brand({
  compact = false,
  inverse = false,
  lightArtwork = "/aquaflow-v2-light.png",
  darkArtwork = "/aquaflow-v2-light.png",
}: {
  compact?: boolean;
  inverse?: boolean;
  lightArtwork?: string;
  darkArtwork?: string;
}) {
  const { theme } = useTheme();
  const useDarkArtwork = inverse || theme === "dark";

  return (
    <span
      className={`brand-lockup${compact ? " brand-lockup--compact" : ""}${useDarkArtwork ? " brand-lockup--dark" : ""}`}
    >
      <Image
        className={`brand-logo${useDarkArtwork ? " brand-logo--dark" : ""}`}
        src={useDarkArtwork ? darkArtwork : lightArtwork}
        width={2172}
        height={724}
        alt="AquaFlow"
        priority
      />
    </span>
  );
}

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      className="theme-toggle"
      type="button"
      onClick={toggleTheme}
      aria-label={theme === "dark" ? "Ativar modo claro" : "Ativar modo escuro"}
      title={theme === "dark" ? "Modo claro" : "Modo escuro"}
    >
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20.2 15.6A8.5 8.5 0 0 1 8.4 3.8 8.7 8.7 0 1 0 20.2 15.6Z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" />
    </svg>
  );
}
