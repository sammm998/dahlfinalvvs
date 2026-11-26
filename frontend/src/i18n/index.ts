/* Språket, med svenskan som nyckel.
 *
 * Gränssnittet är skrivet på svenska och ska fortsätta läsas på svenska i koden - en mängdare och en utvecklare
 * ska kunna tala om samma knapp. Därför är nyckeln den svenska texten själv, inte en uppfunnen kod: `t("Mängder")`
 * ger "Quantities" på engelska och "Mängder" på svenska, och en sträng som ingen hunnit översätta visas på
 * svenska i stället för att försvinna eller visa sin nyckel. Översättning blir något man lägger till, aldrig
 * något som kan gå sönder.
 *
 * Språkbytet laddar om sidan. Det är med avsikt: ett halvt omritat gränssnitt där några rader bytt språk och
 * andra inte är värre än att vänta en halv sekund, och en omladdning gör att varje sträng i appen - även de i
 * komponenter som inte lyssnar på något - kommer tillbaka på rätt språk.
 *
 * Talformatet följer med: svenska skriver 12,5 m och engelska 12.5 m. Det är inte en detalj i en mängd.
 *
 * Bindningen heter `tr` där den används, inte `t`. Skälet står i docs/SPRAK.md §5: `t` är ett vanligt lokalt
 * namn i den här koden, och där ett lokalt `t` låg i samma räckvidd som ett anrop hit gick anropet dit i
 * stället - osynligt för tsc när värdet är `any`. tools/i18n_check.mjs håller regeln.
 */

import { live } from "./en/live";
import { ram } from "./en/ram";
import { publikt } from "./en/publikt";
import { mangd } from "./en/mangd";
import { projekt } from "./en/projekt";
import { admin } from "./en/admin";
import { cad } from "./en/cad";
import { akademi } from "./en/akademi";
import { innehall } from "./en/innehall";
import { server } from "./en/server";
import { kam } from "./en/kam";

export type Lang = "sv" | "en";

const KEY = "fc.lang";

function initial(): Lang {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "sv" || saved === "en") return saved;
  } catch { /* privat läge eller blockerad lagring: följ webbläsaren i stället */ }
  try {
    return navigator.language.toLowerCase().startsWith("sv") ? "sv" : "en";
  } catch { return "sv"; }
}

export const lang: Lang = initial();
if (typeof document !== "undefined") document.documentElement.lang = lang;

export function setLang(next: Lang): void {
  if (next === lang) return;
  try { localStorage.setItem(KEY, next); } catch { /* kan inte sparas: språket gäller ändå den här sidan */ }
  location.reload();
}

/** Den svenska texten, eller dess engelska motsvarighet när en sådan finns. */
export function t(sv: string): string {
  if (lang === "sv") return sv;
  return EN[sv] ?? sv;
}

/* En sträng med tal i sig. Nyckeln bär platshållare, inte delar:
 *
 *     trf("{0} beteckningar lästa, {1} av dem med en dimension.", n, medDn)
 *
 * Skälet är att en mening inte går att sätta ihop av bitar. "Läser ruta 3 av 12" och "Reading tile 3 of 12"
 * har talen på samma ställen, men "3 av 12 rutor lästa" har dem inte - och den dagen en översättning vill
 * flytta dem måste hela meningen vara nyckeln. Delar man i stället upp den i `t("Läser ruta") + i + t("av")`
 * är ordföljden låst till svenskan för alltid.
 */
export function trf(sv: string, ...args: (string | number)[]): string {
  return t(sv).replace(/\{(\d+)\}/g, (_, i) => String(args[Number(i)] ?? ""));
}

/** Ett tal som språket skriver det: 12,5 på svenska, 12.5 på engelska. */
export function num(v: number, decimals = 2): string {
  return v.toLocaleString(lang === "sv" ? "sv-SE" : "en-GB",
    { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export const locale = () => (lang === "sv" ? "sv-SE" : "en-GB");

/* Ordboken, en del per område. Delad för att en översättningsomgång ska röra en fil och inte allas,
 * och sammanslagen en gång när modulen laddas: uppslagningen sker under rendering och får inte kosta
 * något. Står samma nyckel i två delar med olika engelska säger tools/i18n_check.mjs ifrån. */
const EN: Record<string, string> = {
  ...ram,
  ...live,
  ...publikt,
  ...mangd,
  ...projekt,
  ...kam,
  ...admin,
  ...cad,
  ...akademi,
  ...innehall,
  ...server,
};
