"use client";
import { Monitor, Moon, Sun } from "lucide-react";
import * as React from "react";
import { Button } from "./button";
import { DropdownContent, DropdownItem, DropdownMenu, DropdownTrigger } from "./menus";

type Pref = "light" | "dark" | "system";
const Ctx = React.createContext<{ pref: Pref; resolved: "light" | "dark"; setPref: (p: Pref) => void }>({ pref: "system", resolved: "light", setPref: () => {} });
export const useTheme = () => React.useContext(Ctx);

/** Runs before hydration to avoid a flash of the wrong theme. */
export const themeScript = `(function(){try{var p=localStorage.getItem('theme')||'system';var d=p==='dark'||(p==='system'&&matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',d);document.documentElement.style.colorScheme=d?'dark':'light'}catch(e){}})()`;

export function ThemeProvider({ children, initial }: { children: React.ReactNode; initial?: Pref }) {
  const [pref, setPrefState] = React.useState<Pref>("system");
  const [resolved, setResolved] = React.useState<"light" | "dark">("light");
  const apply = React.useCallback((p: Pref) => {
    const dark = p === "dark" || (p === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
    setResolved(dark ? "dark" : "light");
  }, []);
  React.useEffect(() => {
    const stored = (localStorage.getItem("theme") as Pref | null) ?? initial ?? "system";
    setPrefState(stored); apply(stored);
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const on = () => { if ((localStorage.getItem("theme") ?? "system") === "system") apply("system"); };
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [apply, initial]);
  const setPref = React.useCallback((p: Pref) => { localStorage.setItem("theme", p); setPrefState(p); apply(p); }, [apply]);
  return <Ctx.Provider value={{ pref, resolved, setPref }}>{children}</Ctx.Provider>;
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
