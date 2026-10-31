import { useEffect, useState } from "react";

import { effectiveTheme, getChoice, setChoice, ThemeChoice } from "../theme";

/** Header switch between light and dark. "Same as device" lives in Settings. */
export function useThemeChoice(): [ThemeChoice, (c: ThemeChoice) => void] {
  const [choice, setLocal] = useState<ThemeChoice>(getChoice);
  useEffect(() => {
    const onChange = (e: Event) => setLocal((e as CustomEvent<ThemeChoice>).detail);
    window.addEventListener("cv:theme", onChange);
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    const onSystem = () => setLocal(getChoice()); // re-render so the icon matches the device
    mq?.addEventListener?.("change", onSystem);
    return () => {
      window.removeEventListener("cv:theme", onChange);
      mq?.removeEventListener?.("change", onSystem);
    };
  }, []);
  return [choice, setChoice];
}

export default function ThemeToggle() {
  const [choice, set] = useThemeChoice();
  const dark = effectiveTheme(choice) === "dark";
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => set(dark ? "light" : "dark")}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      title={dark ? "Switch to light mode" : "Switch to dark mode"}
    >
      {dark ? (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <circle cx="12" cy="12" r="4.2" />
          <path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" strokeLinecap="round" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}
