"use client";
import { Monitor, Moon, Sun } from "lucide-react";
import * as React from "react";
import { Button } from "./button";
import { DropdownContent, DropdownItem, DropdownMenu, DropdownTrigger } from "./menus";

type Pref = "light" | "dark" | "system";

/** The app's colour, picked per person in Settings. It recolours buttons, highlights and the background glow in both themes
    (tokens in styles.css under `[data-accent]`). The landing page keeps its own colours. */
export const ACCENTS = [
  { value: "blue", label: "Blue", swatch: "#2a4fd6" },
  { value: "violet", label: "Violet", swatch: "#6d3fd9" },
  { value: "teal", label: "Teal", swatch: "#0f766e" },
  { value: "rose", label: "Rose", swatch: "#c42a55" },
  { value: "amber", label: "Amber", swatch: "#b84f0a" },
] as const;
export type Accent = (typeof ACCENTS)[number]["value"];
const isAccent = (v: unknown): v is Accent => ACCENTS.some((a) => a.value === v);

type ThemeCtx = { pref: Pref; resolved: "light" | "dark"; setPref: (p: Pref) => void; accent: Accent; setAccent: (a: Accent) => void };
const Ctx = React.createContext<ThemeCtx>({ pref: "system", resolved: "light", setPref: () => {}, accent: "blue", setAccent: () => {} });
export const useTheme = () => React.useContext(Ctx);

/** Runs before hydration to avoid a flash of the wrong theme or colour. */
export const themeScript = `(function(){try{var p=localStorage.getItem('theme')||'system';var d=p==='dark'||(p==='system'&&matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',d);document.documentElement.style.colorScheme=d?'dark':'light';var a=localStorage.getItem('accent');if(a&&a!=='blue')document.documentElement.dataset.accent=a}catch(e){}})()`;

function applyAccent(a: Accent) {
  if (a === "blue") delete document.documentElement.dataset.accent; else document.documentElement.dataset.accent = a;
}

export function ThemeProvider({ children, initial }: { children: React.ReactNode; initial?: Pref }) {
  const [pref, setPrefState] = React.useState<Pref>("system");
  const [resolved, setResolved] = React.useState<"light" | "dark">("light");
  const [accent, setAccentState] = React.useState<Accent>("blue");
  const apply = React.useCallback((p: Pref) => {
    const dark = p === "dark" || (p === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
    setResolved(dark ? "dark" : "light");
  }, []);
  React.useEffect(() => {
    const stored = (localStorage.getItem("theme") as Pref | null) ?? initial ?? "system";
    setPrefState(stored); apply(stored);
    const a = localStorage.getItem("accent"); if (isAccent(a)) { setAccentState(a); applyAccent(a); }
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const on = () => { if ((localStorage.getItem("theme") ?? "system") === "system") apply("system"); };
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [apply, initial]);
  const setPref = React.useCallback((p: Pref) => { localStorage.setItem("theme", p); setPrefState(p); apply(p); }, [apply]);
  const setAccent = React.useCallback((a: Accent) => { if (!isAccent(a)) return; localStorage.setItem("accent", a); setAccentState(a); applyAccent(a); }, []);
  return <Ctx.Provider value={{ pref, resolved, setPref, accent, setAccent }}>{children}</Ctx.Provider>;
}

/** Pins `resolved` for a subtree (e.g. a page that is always dark) without touching the user's saved preference. */
export function ForceTheme({ resolved, children }: { resolved: "light" | "dark"; children: React.ReactNode }) {
  const parent = useTheme();
  return <Ctx.Provider value={{ ...parent, resolved }}>{children}</Ctx.Provider>;
}

export function ThemeToggle({ onChange }: { onChange?: (p: Pref) => void }) {
  const { pref, resolved, setPref } = useTheme();
  const set = (p: Pref) => { setPref(p); onChange?.(p); };
  return (
    <DropdownMenu>
      <DropdownTrigger asChild><Button variant="ghost" size="icon" aria-label="Change theme">{resolved === "dark" ? <Moon /> : <Sun />}</Button></DropdownTrigger>
      <DropdownContent>
        {([["light", "Light", <Sun key="s" />], ["dark", "Dark", <Moon key="m" />], ["system", "System", <Monitor key="y" />]] as const).map(([v, l, i]) => (
          <DropdownItem key={v} icon={i} onSelect={() => set(v)}><span className={pref === v ? "font-semibold text-primary" : ""}>{l}</span></DropdownItem>
        ))}
      </DropdownContent>
    </DropdownMenu>
  );
}
