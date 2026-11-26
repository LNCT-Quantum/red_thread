import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { initialProgress } from "./story";
import { api } from "./api";
import Game from "./Game";
import "./styles.css";

const KEY = "red-thread-local-v3";

// Notes, evidence links, and theories have no backend endpoints, so only these
// player-authored fields remain in localStorage. Case data never comes from here.
function loadProgress() {
  try {
    const p = JSON.parse(localStorage.getItem(KEY));
    if (p && typeof p === "object") return {
      notes: typeof p.notes === "string" ? p.notes.slice(0, 20000) : "",
      links: Array.isArray(p.links) ? p.links.filter(l => l && typeof l.a === "string" && typeof l.b === "string" && typeof l.reason === "string").slice(-100) : [],
      theory: p.theory && typeof p.theory.reason === "string" && Array.isArray(p.theory.evidence) ? p.theory : null,
    };
  } catch { /* Browser storage is optional. */ }
  return initialProgress;
}

function Landing({ startGame, caseInfo }) {
  const [about, setAbout] = useState(false);
  return <main className="landing">
    <section className="landing-copy"><div className="hero-brand"><h1><em>Red</em> Thread</h1><span>AI Detective</span><div className="red-stroke" /></div><p className="lead">An AI-powered detective game</p><p className="muted">{caseInfo ? `${caseInfo.case_id.toUpperCase()}: ${caseInfo.title}` : "Connecting to case files…"}</p><div className="button-row"><button className="btn primary" onClick={startGame} disabled={!caseInfo}>▶ &nbsp; Start Game</button><button className="btn quiet" onClick={() => setAbout(true)} disabled={!caseInfo}>About</button></div></section>
    {about && <div className="modal-backdrop" onClick={() => setAbout(false)}><section className="modal" role="dialog" aria-modal="true" aria-label="About the story" onClick={e => e.stopPropagation()}><button className="icon-button close" onClick={() => setAbout(false)} aria-label="Close">×</button><p className="eyebrow">THE CASE</p><h2>{caseInfo.title}</h2><p>{caseInfo.description}</p><button className="btn primary" onClick={startGame}>Enter the case →</button></section></div>}
  </main>;
}

function App() {
  const [screen, setScreen] = useState("landing");
  const [progress, setProgress] = useState(loadProgress);
  const [caseInfo, setCaseInfo] = useState(null);
  const [startupError, setStartupError] = useState("");

  useEffect(() => {
    // GET /cases returns the available case summaries. Once a playable case is
    // selected, GET /cases/{case_id} supplies its title and public description.
    api("/cases").then(({ items }) => {
      const playable = items.find(item => item.playable);
      if (!playable) throw new Error("No playable case is available.");
      return api(`/cases/${encodeURIComponent(playable.case_id)}`);
    }).then(setCaseInfo).catch(error => setStartupError(error.message));
  }, []);
  // This is deliberately local-only; backend-owned session state is persisted
  // separately by getOrCreateSession in api.js.
  useEffect(() => { try { localStorage.setItem(KEY, JSON.stringify(progress)); } catch { /* Optional local save. */ } }, [progress]);

  if (startupError) return <main className="landing"><section className="modal"><h2>Backend unavailable</h2><p>{startupError}</p><p>Start the backend and refresh this page.</p></section></main>;
  if (screen === "landing") return <Landing caseInfo={caseInfo} startGame={() => setScreen("game")}/>;
  return <Game caseInfo={caseInfo} goHome={() => setScreen("landing")} progress={progress} setProgress={setProgress}/>;
}

createRoot(document.getElementById("root")).render(<App/>);
