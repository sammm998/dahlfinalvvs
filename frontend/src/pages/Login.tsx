import { LangSwitch } from "../components/SiteHeader";
import { useState } from "react";
import { t as tr } from "../i18n";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { usePointerParallax } from "../components/tilt";
import { DahlLogo } from "../components/DahlLogo";

/* The same run as on the front page, drawn small: a labelled pipe and one the drawing does not name. */
function Motif() {
  return (
    <svg viewBox="0 0 470 190" role="img" aria-label={tr("Rör markerade och mätta ur en ritning")}>
      <g stroke="#2f343d" strokeWidth="1.2" fill="none">
        <path d="M20 24 H300 V166 H20 Z M160 24 V166 M20 100 H160" />
      </g>
      <g fill="none" strokeWidth="2.8" strokeLinecap="butt">
        <path d="M46 138 H210 V70 H330" stroke="#00b5e2" strokeOpacity="0.9" strokeDasharray="14 5 2.5 5" />
        <path d="M210 138 H286" stroke="#60a5fa" strokeOpacity="0.85" strokeDasharray="14 5 2.5 5" />
        <path d="M348 132 H438" stroke="#4b5160" strokeDasharray="14 5 2.5 5" />
      </g>
      <g fill="#0a0b0d" strokeWidth="1.8">
        <circle cx="46" cy="138" r="4" stroke="#00b5e2" />
        <circle cx="330" cy="70" r="4" stroke="#00b5e2" />
        <circle cx="286" cy="138" r="4" stroke="#60a5fa" />
      </g>
      <g fontFamily="ui-monospace, SFMono-Regular, monospace">
        <path d="M414 62 H344 L332 70" stroke="#00b5e2" strokeOpacity="0.45" strokeWidth="1" fill="none" />
        <text x="344" y="40" fill="#f0f2f5" fontSize="12.5">S1-P5-110</text>
        <text x="344" y="56" fill="#8b929e" fontSize="11.5">24,8 m</text>
        <text x="348" y="122" fill="#5b616c" fontSize="11.5">{tr("onämnd")}</text>
      </g>
    </svg>
  );
}

export default function Login() {
  // the panel beside the form is a scene, not a picture: the motif, the principle and the figures sit at three
  // depths and shift with the pointer, so the page has somewhere to be looked into
  const pp = usePointerParallax();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  /* Den som klickade på "Mängda" ute på sajten ville till mängdningen, inte till projektlistan. Vägen dit
     bär med sig vart den var på väg, och efter inloggningen fortsätter resan. Bara adresser inom sajten
     följs - en `next` som pekar ut på nätet är inte en väg tillbaka utan en vidarebefordran. */
  const [params] = useSearchParams();
  const next = params.get("next");
  const efterat = next && next.startsWith("/") && !next.startsWith("//") ? next : "/projekt";
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      if (mode === "login") await api.login(email, password);
      else await api.register(email, password);
      nav(efterat);
    } catch (ex: any) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="auth">
      <LangSwitch className="login-language" />
      <div className="auth-form">
        <form onSubmit={submit}>
          <a href="/" className="auth-logo" aria-label="Dahl"><DahlLogo height={26} /></a>
          <h1>{mode === "login" ? tr("Logga in") : tr("Skapa konto")}</h1>
          <p className="sub">
            {mode === "login"
              ? tr("Ladda upp en VVS-ritning och få mängden med beläggen kvar.")
              : tr("Ett konto räcker för att köra en första ritning och jämföra mot din egen handmängdning.")}
          </p>

          <div className="field">
            <label htmlFor="lg-email">{tr("E-post")}</label>
            <input
              id="lg-email"
              placeholder={tr("namn@foretag.se")}
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="lg-pw">{tr("Lösenord")}</label>
            <input
              id="lg-pw"
              placeholder="••••••••"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {err && <p className="error">{err}</p>}

          <button type="submit" disabled={busy}>
            {busy ? tr("Ett ögonblick…") : mode === "login" ? tr("Logga in") : tr("Registrera")}
          </button>

          <p className="swap">
            {mode === "login" ? tr("Har du inget konto? ") : tr("Har du redan ett konto? ")}
            <button type="button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setErr(""); }}>
              {mode === "login" ? tr("Skapa ett") : tr("Logga in")}
            </button>
          </p>
        </form>
      </div>

      <aside className="aside" style={{ perspective: "1200px" }}>
        <div className="auth-plane" style={{ transform: `translate3d(${pp.x * 16}px, ${pp.y * 9}px, 40px) rotateY(${pp.x * -3}deg) rotateX(${pp.y * 2.2}deg)` }}>
          <Motif />
        </div>
        <div className="auth-plane" style={{ transform: `translate3d(${pp.x * 7}px, ${pp.y * 4}px, 0)` }}>
          <blockquote>
            Tvetydigt är ett giltigt svar. Fel säkerhet är det inte.
          </blockquote>
          <div className="who">{tr("Principen hela motorn är byggd kring")}</div>
        </div>
        <div className="facts">
          <div>
            <b>{tr("Spårbart")}</b>
            {tr("mängder med ritningsgeometri")},
            <br />
            {tr("beteckning och skala")}
          </div>
          <div>
            <b>{tr("Granskningsbart")}</b>
            {tr("visa osäkra sträckor")},
            <br />
            {tr("rätta och exportera")}
          </div>
          <div>
            <b>{tr("Ritningsberoende")}</b>
            {tr("kontrollera resultatet")}
            <br />
            {tr("före kalkyl och beställning")}
          </div>
        </div>
      </aside>
    </div>
  );
}
