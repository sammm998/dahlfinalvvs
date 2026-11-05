import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { prefersStill } from "./lp-smooth";

/* Ridån mellan sidorna.
 *
 * Det som gör en samling sidor till en plats är att man aldrig ser dem blinka förbi. En ridå går över bilden,
 * sidan byts bakom den, och den går undan igen - och eftersom bytet sker medan den täcker ser man aldrig den
 * halvbyggda sidan, bara att man kommit någonstans.
 *
 * Bytet sker i mitten av rörelsen, inte i början: React har redan bytt sidan när ridån täcker, så det som
 * göms är just ögonblicket då den nya sidan sätter sig och skrollen går till toppen.
 *
 * Bara publika sidor. Inne i verktyget byter man flik, inte rum, och en ridå mellan två flikar i samma
 * arbetsbord är i vägen. Den som bett om mindre rörelse får inget alls.
 */

const HALF = 460;          // hur länge ridån går in, och lika länge ut

export default function PageCurtain({ label }: { label?: string }) {
  const { pathname } = useLocation();
  const [state, setState] = useState<"vila" | "in" | "ut">("vila");
  const first = useRef(true);
  const seen = useRef(pathname);

  useEffect(() => {
    if (first.current) { first.current = false; seen.current = pathname; return; }
    if (pathname === seen.current) return;
    seen.current = pathname;
    if (prefersStill()) return;
    setState("in");
    const a = setTimeout(() => setState("ut"), HALF);
    const b = setTimeout(() => setState("vila"), HALF * 2);
    return () => { clearTimeout(a); clearTimeout(b); };
  }, [pathname]);

  if (state === "vila") return null;
  return (
    <div className={`pc pc-${state}`} aria-hidden="true">
      <span className="pc-mark">{label || "Dahl"}</span>
    </div>
  );
}
