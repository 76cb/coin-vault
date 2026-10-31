// Light, dark, or the device's setting. Remembered per browser (it's a display preference, not data).

export type ThemeChoice = "system" | "light" | "dark";
const KEY = "cv-theme";

export function getChoice(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function effectiveTheme(choice: ThemeChoice = getChoice()): "light" | "dark" {
  if (choice !== "system") return choice;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(choice: ThemeChoice = getChoice()): void {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
  const meta = document.querySelector('meta[name="theme-color"]');
  meta?.setAttribute("content", effectiveTheme(choice) === "dark" ? "#08101d" : "#0f1b2d");
}

export function setChoice(choice: ThemeChoice): void {
  try {
    if (choice === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, choice);
  } catch {
    /* private mode: the choice lasts until the page is closed */
  }
  applyTheme(choice);
  window.dispatchEvent(new CustomEvent("cv:theme", { detail: choice }));
}

// How collection tiles show a photo: filling the square tile (cropped at the edges) or whole inside it.
export type PhotoFit = "fill" | "whole";
const FIT_KEY = "cv-photo-fit";

export function getPhotoFit(): PhotoFit {
  try {
    return localStorage.getItem(FIT_KEY) === "whole" ? "whole" : "fill";
  } catch {
    return "fill";
  }
}

export function applyPhotoFit(fit: PhotoFit = getPhotoFit()): void {
  document.documentElement.setAttribute("data-photo-fit", fit);
}

export function setPhotoFit(fit: PhotoFit): void {
  try {
    if (fit === "fill") localStorage.removeItem(FIT_KEY);
    else localStorage.setItem(FIT_KEY, fit);
  } catch {
    /* private mode: lasts until the page is closed */
  }
  applyPhotoFit(fit);
}
