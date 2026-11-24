import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { initialProgress } from "./story";
import Game from "./Game";
import "./styles.css";

// Browser-storage key for this preview's locally persisted investigation progress.
const KEY = "red-thread-demo-v2";

// Restores saved progress defensively and sanitizes every browser-controlled value.
function loadProgress() {
  try {
    const p = JSON.parse(localStorage.getItem(KEY));
    if (p && typeof p === "object") {
      const found = Array.isArray(p.found) ? p.found.filter(id => typeof id === "string" && /^0[1-9]$|^10$/.test(id)) : [];
      const interviews = {};
      for (const id of ["anaya", "kabir", "nisha"]) {
        interviews[id] = Array.isArray(p.interviews?.[id])
          ? p.interviews[id].filter(m => m && typeof m.question === "string" && typeof m.answer === "string").slice(-100).map(m => ({question:m.question.slice(0,240),answer:m.answer.slice(0,1000)}))
          : [];
      }
      return {
        found: [...new Set(["01", ...found])],
        notes: typeof p.notes === "string" ? p.notes.slice(0, 20000) : "",
        interviews,
        links: Array.isArray(p.links) ? p.links.filter(l => l && typeof l.a === "string" && typeof l.b === "string" && typeof l.reason === "string").slice(-100) : [],
        theory: p.theory && typeof p.theory === "object" && typeof p.theory.reason === "string" && Array.isArray(p.theory.evidence) ? p.theory : null,
      };
    }
  } catch { /* Browser storage can be unavailable. */ }
  return initialProgress;
}

// Public welcome screen. Both primary actions open the game dashboard directly.
function Landing({ startGame }) {
  const [about, setAbout] = useState(false);
  return <main className="landing">
    <section className="landing-copy"><div className="hero-brand"><h1><em>Red</em> Thread</h1><span>AI Detective</span><div className="red-stroke" /></div><p className="lead">An AI-powered detective game</p><p className="muted">The Last Three Days · Case 001: The Silent Witness</p><div className="button-row"><button className="btn primary" onClick={startGame}>▶ &nbsp; Start Game</button><button className="btn quiet" onClick={() => setAbout(true)}>About</button></div></section>
    {about && <div className="modal-backdrop" onClick={() => setAbout(false)}><section className="modal" role="dialog" aria-modal="true" aria-label="About the story" onClick={e => e.stopPropagation()}><button className="icon-button close" onClick={() => setAbout(false)} aria-label="Close">×</button><p className="eyebrow">THE CASE</p><h2>The Puppeteer returns</h2><p>Eighteen months after his family was murdered, Detective Aarav Mehra receives a new threat. Psychologist Dr. Rishabh Malhotra has been found poisoned, and the killer promises three more deaths in three days.</p><p>Explore the first case and keep evidence separate from suspicion.</p><button className="btn primary" onClick={startGame}>Enter the case →</button></section></div>}
  </main>;
}

// Root screen controller: switches directly between the landing page and game dashboard.
function App() {
  const [screen, setScreen] = useState("landing");
  const [progress, setProgress] = useState(loadProgress);

  // Saves every progress change locally so a browser refresh does not reset the case.
  useEffect(() => { try { localStorage.setItem(KEY, JSON.stringify(progress)); } catch { /* Optional local save. */ } }, [progress]);

  if (screen === "landing") return <Landing startGame={() => setScreen("game")}/>;
  return <Game goHome={() => setScreen("landing")} progress={progress} setProgress={setProgress}/>;
}

// Mount the React application into the root element supplied by index.html.
createRoot(document.getElementById("root")).render(<App/>);
