import AiModelDialog from "./components/AiModelDialog";
import { useEffect, useState } from "react";
import { t as tr, trf, locale } from "./i18n";
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, getToken, setToken, currentEmail, flushEvents, track } from "./api";
import Landing from "./pages/Landing";
import Home from "./fc/Home";
import { PlatformPage, VprPage } from "./fc/Platform";
import { AcademyCourse, AcademyHome, AcademyLesson } from "./academy/Academy";
import { ExamPage, QuizPage } from "./academy/Exam";
import { CertificatePage, VerifyPage } from "./academy/Certificate";
import Login from "./pages/Login";
import Docs from "./pages/Docs";
import Projects from "./pages/Projects";
import ProjectPage from "./pages/Project";
import DrawingPage from "./pages/Drawing";
import AnalysisPage from "./pages/Analysis";
import { LangSwitch } from "./components/SiteHeader";
import Boundary from "./components/Boundary";
import PageCurtain from "./components/PageCurtain";
import LearnPage, { LearnCoursePage, LearnLessonPage } from "./pages/LearnPage";
import MaterialPage from "./pages/Material";
import CreditsPage from "./pages/Credits";
import PricingPage from "./pages/Pricing";
import AboutPage from "./pages/About";
import HowItWorksPage from "./pages/HowItWorks";
import ArchitecturePage from "./pages/Architecture";
import EducationPage, { EducationCoursePage, EducationLessonPage } from "./pages/Education";
import FeaturePage from "./pages/Feature";
import ContactPage from "./pages/Contact";
import AdminPage from "./pages/Admin";
import ProjectAnalysisPage from "./pages/ProjectAnalysis";
import CalcPage from "./pages/CalcPage";
import TakeoffPage from "./pages/Takeoff";
import TakeoffPickPage from "./pages/TakeoffPick";
import BuildingCadPage from "./pages/BuildingCad";
import AgentPage from "./pages/Agent";
import CadPickPage from "./pages/CadPick";
import { DahlLogo, DahlMark } from "./components/DahlLogo";

function Guard({ children }: { children: JSX.Element }) {
  return getToken() ? children : <Navigate to="/login" replace />;
}

function IconProjects() {
  return (
    <svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <rect x="2.5" y="4.5" width="10" height="11" stroke="currentColor" strokeWidth="1.3" />
      <path d="M5.5 2.5h10v11" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  );
}

function IconRail() {
  return (
    <svg width="16" height="16" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <rect x="2.5" y="3.5" width="13" height="11" stroke="currentColor" strokeWidth="1.3" />
      <path d="M7 3.5v11" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  );
}

function IconCredits() {
  return (
    <svg width="18" height="18" viewBox="0 0 22 22" aria-hidden="true">
      <circle cx="11" cy="11" r="7.5" stroke="currentColor" strokeWidth="1.8" fill="none" />
      <path d="M8.5 13.2c.6.9 1.5 1.3 2.6 1.3 1.6 0 2.6-.8 2.6-2 0-2.6-5-1.3-5-3.9 0-1.1.9-1.9 2.4-1.9 1 0 1.8.4 2.3 1.1" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" />
      <path d="M11 5.8v1.6M11 14.6v1.6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
function IconMaterial() {
  return (
    <svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M2.4 5.6 9 2.4l6.6 3.2v6.8L9 15.6 2.4 12.4V5.6Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M2.4 5.6 9 8.9l6.6-3.3M9 8.9v6.7" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  );
}

function IconLearn() {
  return (
    <svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M2.5 5.2 9 2.5l6.5 2.7L9 8 2.5 5.2Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M5 6.7v4.1c0 1.2 1.8 2.2 4 2.2s4-1 4-2.2V6.7" stroke="currentColor" strokeWidth="1.3" />
      <path d="M15.5 5.4v4.2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

function IconRuler() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="8" width="20" height="8" rx="1.5" />
      <path d="M6 8v3M10 8v4M14 8v3M18 8v4" />
    </svg>
  );
}

/** Rummet hette Granska innan det blev CAD. En sparad länk ska öppna samma blad, inte en tom sida. */
function GranskaRedirect() {
  const { id } = useParams();
  return <Navigate to={id ? `/mangda/${id}` : "/mangda"} replace />;
}

function IconCad() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 3.5h11l5 5V20a.5.5 0 0 1-.5.5h-15A.5.5 0 0 1 4 20V3.5Z" />
      <path d="M14.5 3.6V9h5.2" />
      <path d="m8 14.2 2.3 2.3 4.4-4.6" />
    </svg>
  );
}

function IconAgent() {
  return (
    <svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M3 4.5h12v8H8l-3.5 3v-3H3z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <circle cx="6.5" cy="8.5" r="0.9" fill="currentColor" /><circle cx="9" cy="8.5" r="0.9" fill="currentColor" /><circle cx="11.5" cy="8.5" r="0.9" fill="currentColor" />
    </svg>
  );
}
function IconAdmin() {
  return (
    <svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M9 1.8 15.2 4v4.6c0 3.6-2.5 6.6-6.2 7.6-3.7-1-6.2-4-6.2-7.6V4L9 1.8Z"
        stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M6.6 9 8.4 10.8 11.6 7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconOut() {
  return (
    <svg width="15" height="15" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M11 3.5H4.5v11H11M8 9h7m0 0-2.5-2.5M15 9l-2.5 2.5" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  );
}

const ROUTES = (
  <Boundary what="sidan">
  <Routes>
    <Route path="/" element={<Home />} />
    {/* Den förra startsidan ligger kvar under eget namn tills varje avsnitt som är värt att
        behålla flyttat in i den nya. Ingen länk pekar hit; den är för jämförelse. */}
    <Route path="/klassisk" element={<Landing />} />
    <Route path="/login" element={<Login />} />
    <Route path="/dokumentation" element={<Docs />} />
    {/* Plattformen och VPR stod i menyn men hade ingen rutt: den som klickade föll igenom till startsidan
        igen. Nu finns rummen de pekade på. */}
    <Route path="/plattformen" element={<PlatformPage />} />
    <Route path="/vpr" element={<VprPage />} />
    <Route path="/priser" element={<PricingPage />} />
    <Route path="/om-oss" element={<AboutPage />} />
    <Route path="/hur-det-funkar" element={<HowItWorksPage />} />
    <Route path="/architecture" element={<ArchitecturePage />} />
    <Route path="/funktioner/:slug" element={<FeaturePage />} />
    <Route path="/utbildning" element={<EducationPage />} />
    <Route path="/utbildning/:modul" element={<EducationCoursePage />} />
    <Route path="/utbildning/:modul/:lektion" element={<EducationLessonPage />} />
    <Route path="/kontakt" element={<ContactPage />} />
    {/* Dahl Academy. Verifieringen är öppen med flit: ett certifikat som bara innehavaren kan visa
        bevisar ingenting. Allt annat kräver konto. */}
    <Route path="/verifiera" element={<VerifyPage />} />
    <Route path="/academy" element={<Guard><AcademyHome /></Guard>} />
    <Route path="/academy/lektion/:id" element={<Guard><AcademyLesson /></Guard>} />
    <Route path="/academy/tenta/:slug" element={<Guard><ExamPage /></Guard>} />
    <Route path="/academy/:kurs" element={<Guard><AcademyCourse /></Guard>} />
    <Route path="/academy/:kurs/:modul/quiz" element={<Guard><QuizPage /></Guard>} />
    <Route path="/certifikat/:code" element={<Guard><CertificatePage /></Guard>} />
    <Route path="/projekt" element={<Guard><Projects /></Guard>} />
    <Route path="/projects/:id" element={<Guard><ProjectPage /></Guard>} />
    <Route path="/projects/:id/analys" element={<Guard><ProjectAnalysisPage /></Guard>} />
    <Route path="/drawings/:id" element={<Guard><DrawingPage /></Guard>} />
    <Route path="/jobs/:id" element={<Guard><AnalysisPage /></Guard>} />
    <Route path="/jobs/:id/kalkyl" element={<Guard><CalcPage /></Guard>} />
    <Route path="/mangda" element={<Guard><TakeoffPickPage /></Guard>} />
    <Route path="/mangda/:id" element={<Guard><TakeoffPage /></Guard>} />
    <Route path="/cad" element={<Guard><CadPickPage /></Guard>} />
    <Route path="/cad/:id" element={<Guard><BuildingCadPage /></Guard>} />
    {/* Granskningen av någon annans ritning bor i Mängda - CAD är ritbordet. Gamla länkar till båda rummen
        pekar dit markeringarna faktiskt ligger. */}
    <Route path="/granska" element={<Navigate to="/mangda" replace />} />
    <Route path="/granska/:id" element={<GranskaRedirect />} />
    <Route path="/lar" element={<Guard><LearnPage /></Guard>} />
    <Route path="/lar/:modul" element={<Guard><LearnCoursePage /></Guard>} />
    <Route path="/lar/:modul/:lektion" element={<Guard><LearnLessonPage /></Guard>} />
    <Route path="/agent" element={<Guard><AgentPage /></Guard>} />
    <Route path="/material" element={<Guard><MaterialPage /></Guard>} />
    <Route path="/credits" element={<Guard><CreditsPage /></Guard>} />
    <Route path="/installningar" element={<Navigate to="/admin" replace />} />
    <Route path="/admin" element={<Guard><AdminPage /></Guard>} />
  </Routes>
  </Boundary>
);

export default function App() {
  const nav = useNavigate();
  // Admin-länken visas bara för den som är admin, och rollen kommer från servern och inte från något
  // webbläsaren kan hitta på. Att dölja länken är ingen spärr - spärren sitter på varje route i tjänsten -
  // men en länk som leder till ett nej är ett dåligt gränssnitt.
  const [role, setRole] = useState<string | null>(null);
  const { pathname } = useLocation();
  useEffect(() => {
    if (!getToken()) { setRole(""); return; }
    api.myRole().then((r) => setRole(r.role)).catch(() => setRole(""));
  }, [pathname]);
  // den gemensamma budgeten: alla som är inloggade ser vad som är kvar, direkt i sidopanelen
  const [budget, setBudget] = useState<any>(null);
  useEffect(() => {
    if (!getToken()) { setBudget(null); return; }
    api.credits().then((r) => setBudget(r.budget ?? null)).catch(() => setBudget(null));
  }, [pathname]);
  const left: number | null = budget ? budget.remaining_kr : null;

  // Vad besökaren gjorde. En klick sparas som en ruta i fönstret och inte som en punkt på en skärm: andelar
  // av bredden och höjden, så att bilden gäller alla skärmstorlekar på en gång. Det som skickas med är vad
  // som klickades - knappens text eller dess roll - och aldrig vad som stod i ett fält.
  useEffect(() => { track({ name: "sidvisning", path: pathname }); }, [pathname]);
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const el = (e.target as HTMLElement)?.closest?.("button, a, input, select, textarea, [role]");
      const tag = el ? el.tagName.toLowerCase() : "";
      // ett fälts innehåll är användarens, inte tjänstens: bara sorten sparas
      const what = !el ? "" : tag === "input" || tag === "textarea" || tag === "select"
        ? `${tag}:${(el as HTMLInputElement).type || tag}`
        : `${tag}:${(el.textContent || "").trim().slice(0, 60)}`;
      track({
        name: "klick",
        x: e.clientX / Math.max(window.innerWidth, 1),
        y: e.clientY / Math.max(window.innerHeight, 1),
        target: what,
      });
    };
    // en flik som stängs mitt i en hink tar hinken med sig; sendBeacon hinner före
    const onHide = () => { if (document.visibilityState === "hidden") flushEvents(true); };
    window.addEventListener("click", onClick, { capture: true });
    document.addEventListener("visibilitychange", onHide);
    return () => {
      window.removeEventListener("click", onClick, { capture: true } as any);
      document.removeEventListener("visibilitychange", onHide);
      flushEvents();
    };
  }, []);
  const [rail, setRail] = useState<boolean>(() => {
    try { return localStorage.getItem("vvs.rail") === "1"; } catch { return false; }
  });
  const toggleRail = () => setRail((v) => {
    try { localStorage.setItem("vvs.rail", v ? "0" : "1"); } catch { /* private window */ }
    return !v;
  });
  // the landing page and the login screen bring their own layout
  // a trailing slash is the same page: without this, /dokumentation/ fell through and got the app's sidebar
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  const PUBLIC = ["", "/", "/login", "/dokumentation", "/priser", "/om-oss", "/hur-det-funkar", "/utbildning",
                  "/kontakt", "/plattformen", "/vpr", "/architecture"];
  // Akademins kurser och föreläsningar ligger under /utbildning och bär sin egen ram, precis som katalogen.
  if (PUBLIC.includes(path) || path.startsWith("/utbildning/") || path.startsWith("/funktioner/"))
    return <><PageCurtain />{ROUTES}</>;
  const email = currentEmail();
  // On a reading, the drawing is the page. The sidebar carries one link and a sign-out; on a wide sheet those
  // 244 px are the difference between seeing the whole drawing and hunting across it, so this route opens with
  // the sidebar folded to its rail. It is still one click away, and a reader who unfolds it keeps it unfolded.
  const chosen = (() => { try { return localStorage.getItem("vvs.rail") !== null; } catch { return false; } })();
  const railed = rail || (!chosen && (path.startsWith("/jobs/") || (path.startsWith("/cad/") && path !== "/cad")));
  return (
    <div className={`app${railed ? " railed" : ""}`}>
      <AiModelDialog />
      <aside className="side">
        <button className="ghost small railbtn" onClick={toggleRail}
          title={rail ? tr("Visa sidopanelen") : tr("Fäll ihop sidopanelen")}
          aria-label={rail ? tr("Visa sidopanelen") : tr("Fäll ihop sidopanelen")}><IconRail /></button>
        <div>
          <Link to="/projekt" className="brand" aria-label="Dahl"><span className="rail-only"><DahlMark size={22} /></span><span className="wide"><DahlLogo height={20} /></span></Link>
          <div className="org wide" style={{ marginTop: 10 }}>{tr("Mängdning ur ren vektor")}</div>
        </div>
        <nav>
          <Link to="/projekt" className={path.startsWith("/projekt") || path.startsWith("/projects") ? "on" : ""}>
            <IconProjects /> <span className="wide">{tr("Projekt")}</span>
          </Link>
          <Link to="/lar" className={path.startsWith("/lar") ? "on" : ""}>
            <IconLearn /> <span className="wide">{tr("Lär dig VVS")}</span>
          </Link>
          <Link to="/mangda" className={path.startsWith("/mangda") ? "on" : ""}>
            <IconRuler /> <span className="wide">{tr("Mängda")}</span>
          </Link>
          <Link to="/cad" className={path.startsWith("/cad") || path.startsWith("/granska") ? "on" : ""}>
            <IconCad /> <span className="wide">CAD</span>
          </Link>
          <Link to="/agent" className={path.startsWith("/agent") ? "on" : ""}>
            <IconAgent /> <span className="wide">Agent</span>
          </Link>
          <Link to="/material" className={path.startsWith("/material") ? "on" : ""}>
            <IconMaterial /> <span className="wide">{tr("Material")}</span>
          </Link>
          <Link to="/credits" className={path.startsWith("/credits") ? "on" : ""}>
            <IconCredits /> <span className="wide">Credits{left !== null && (
              <span className="muted small" style={{ marginLeft: 6 }} title={tr("Kvar av den gemensamma budgeten")}>
                {trf("{0} kr kvar", Math.round(left).toLocaleString(locale()))}
              </span>)}</span>
          </Link>
          {(role === "admin" || role === "partner") && (
            <Link to="/admin" className={path.startsWith("/admin") ? "on" : ""}>
              <IconAdmin /> <span className="wide">{tr(role === "admin" ? "Administration" : "Min provision")}</span>
            </Link>
          )}
        </nav>
        <div className="foot">
          <LangSwitch className="app-language" />
          {email && <div className="who wide">{email}</div>}
          <button className="secondary small" style={{ alignSelf: "flex-start", display: "inline-flex", alignItems: "center", gap: 8 }}
            onClick={() => { setToken(null); nav("/"); }}>
            <IconOut /> <span className="wide">{tr("Logga ut")}</span>
          </button>
        </div>
      </aside>
      <div className="main">
        {budget && budget.warning >= 80 && (
          // alla inloggade ser samma varning: från 80 %, starkare från 95 %, och när budgeten är slut
          <div role="alert" style={{
            margin: "12px 16px 0", padding: "10px 14px", borderRadius: 8, fontSize: 14,
            background: budget.exhausted ? "#fdecea" : budget.warning >= 95 ? "#fde8d7" : "#fff6d6",
            border: `1px solid ${budget.exhausted ? "#e6a09a" : budget.warning >= 95 ? "#ebb48a" : "#ecd27a"}`,
            color: "#3a2a00" }}>
            <b>{budget.exhausted ? tr("AI-budgeten är slut.") : trf("AI-budgeten är till {0} % använd.", Math.floor(budget.used_pct))}</b>{" "}
            {budget.exhausted
              ? tr("AI-funktionerna är pausade för alla tills administratören höjer taket eller nollställer räkningen.")
              : trf("{0} kr kvar av {1} kr, gemensamt för alla.", Math.round(budget.remaining_kr).toLocaleString(locale()), Math.round(budget.limit_kr).toLocaleString(locale()))}{" "}
            <Link to="/credits">{tr("Se vad som använts")}</Link>
          </div>
        )}
        {ROUTES}
      </div>
    </div>
  );
}
