/* Dahls logotyp, ritad direkt ur originalfilen (public/dahl-logo.svg).
 *
 * Ordbilden DAHL tar färgen från texten runt omkring (currentColor), så samma komponent blir marinblå på ljus
 * yta och vit på mörk. De två snedstrecken är alltid Dahl-cyan - det är dem man känner igen märket på.
 * DahlMark är bara snedstrecken, för ställen där ordbilden inte får plats (favicon, smal meny, ikoner). */

export const DAHL_NAVY = "#004976";
export const DAHL_CYAN = "#00B5E2";

function Word() {
  return (
    <g fill="currentColor">
      <path d="M61.77,19.18v6.18c0,1.45-1.16,2.62-2.6,2.62c-1.44,0-2.6-1.17-2.6-2.62V8.16c0-1.45,1.17-2.62,2.6-2.62s2.6,1.17,2.6,2.62v6.58h10.79V8.15c0-1.45,1.16-2.62,2.6-2.62s2.6,1.17,2.6,2.62v17.2c0,1.45-1.16,2.62-2.6,2.62c-1.44,0-2.6-1.17-2.6-2.62v-6.18H61.77L61.77,19.18z" />
      <path d="M102.2,27.84c1.29,0,2.34-1.05,2.34-2.35c0-1.3-1.05-2.36-2.34-2.36H88.93v-15c0-1.45-1.16-2.62-2.6-2.62s-2.6,1.17-2.6,2.62v17.09c0,1.45,1.16,2.62,2.6,2.62H102.2L102.2,27.84z" />
      <path d="M11.69,23.65H5.2V10.15l6.49,0c3.33,0,6.04,3.03,6.04,6.75S15.02,23.65,11.69,23.65L11.69,23.65z M2.6,5.97C1.16,5.97,0,7.13,0,8.58v16.64c0,1.45,1.16,2.62,2.6,2.62h9.31c6,0,10.86-4.89,10.86-10.93S17.91,5.97,11.91,5.97L2.6,5.97L2.6,5.97z" />
      <path d="M42.31,8.14c-0.77-1.33-1.64-2.39-2.9-2.52c-1.71-0.36-3.02,0.28-4.24,2.2l-9.33,16.23c-0.72,1.25-0.29,2.85,0.95,3.58c1.25,0.72,2.84,0.29,3.55-0.96l8.3-14.44l8.29,14.44c0.72,1.25,2.31,1.68,3.55,0.96c1.25-0.72,1.67-2.32,0.95-3.58L42.31,8.14L42.31,8.14z" />
    </g>
  );
}

function Slashes() {
  return (
    <g fill={DAHL_CYAN}>
      <path d="M127.46,23.04c-0.7,1.22-2.24,1.64-3.45,0.93c-1.21-0.71-1.62-2.27-0.92-3.49l8.84-15.64c0.77-1.43,2.24-1.64,3.45-0.93c1.21,0.71,1.62,2.27,0.92,3.49L127.46,23.04z" />
      <path d="M112.89,31.19c-0.7,1.22-2.24,1.64-3.45,0.93c-1.21-0.71-1.62-2.26-0.92-3.49L122.23,4.8c0.7-1.22,2.24-1.64,3.45-0.93c1.21,0.71,1.62,2.27,0.92,3.49L112.89,31.19z" />
    </g>
  );
}

/** Hela logotypen: DAHL//. `height` i pixlar; bredden följer originalets proportioner. */
export function DahlLogo({ height = 20, title, className }: { height?: number | string; title?: string; className?: string }) {
  return (
    <svg className={`dahl-logo${className ? ` ${className}` : ""}`} height={height} width={typeof height === "number" ? (height * 136.64) / 36 : undefined}
      viewBox="0 0 136.64 36" role={title ? "img" : undefined} aria-label={title} aria-hidden={title ? undefined : true}
      style={{ display: "block", flex: "none", aspectRatio: "136.64 / 36" }}>
      <Word />
      <Slashes />
    </svg>
  );
}

/** Bara snedstrecken //. */
export function DahlMark({ size = 18 }: { size?: number }) {
  return (
    <svg className="dahl-mark" width={size} height={size} viewBox="107.4 3.2 30 30" aria-hidden="true"
      style={{ display: "block", flex: "none" }}>
      <Slashes />
    </svg>
  );
}
