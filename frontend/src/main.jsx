import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { caseFile, initialProgress } from "./story";
import Game from "./Game";
import "./styles.css";

const KEY = "red-thread-demo-v2";
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

function GoogleSignIn({ done }) {
  const [message, setMessage] = useState("");
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID?.trim();
  function start() {
    if (!clientId) { setMessage("Google sign-in needs a Web OAuth client ID. You can use Guest Preview now."); return; }
    if (!window.google?.accounts?.oauth2) { setMessage("Google could not load. Check your connection or browser settings."); return; }
    setMessage("Opening Google sign-in…");
    window.google.accounts.oauth2.initTokenClient({
      client_id: clientId, scope: "openid email profile",
      callback: async (response) => {
        if (!response.access_token || response.error) { setMessage("Sign-in was cancelled or failed."); return; }
        try {
          const result = await fetch("https://openidconnect.googleapis.com/v1/userinfo", { headers: { Authorization: "Bearer " + response.access_token } });
          if (!result.ok) throw Error("Profile unavailable");
          const profile = await result.json();
          if (!profile.sub || !profile.email) throw Error("Incomplete profile");
          done({ name: profile.name || profile.email, mode: "google" });
        } catch { setMessage("Could not load your Google profile. Please try again."); }
      },
      error_callback: () => setMessage("Google sign-in popup was closed or blocked."),
    }).requestAccessToken({ prompt: "select_account" });
  }
  return <><button className="google-button" type="button" onClick={start}><b>G</b> Continue with Google</button>{message && <p role="status" className="inline-message">{message}</p>}</>;
}

function Landing({ navigate }) {
  const [about, setAbout] = useState(false);
  return <main className="landing">
    <section className="landing-copy"><div className="hero-brand"><h1><em>Red</em> Thread</h1><span>AI Detective</span><div className="red-stroke" /></div><p className="lead">An AI-powered detective game</p><p className="muted">The Last Three Days · Case 001: The Silent Witness</p><div className="button-row"><button className="btn primary" onClick={() => navigate("login")}>▶ &nbsp; Play Now</button><button className="btn quiet" onClick={() => setAbout(true)}>About</button></div></section>
    {about && <div className="modal-backdrop" onClick={() => setAbout(false)}><section className="modal" role="dialog" aria-modal="true" aria-label="About the story" onClick={e => e.stopPropagation()}><button className="icon-button close" onClick={() => setAbout(false)} aria-label="Close">×</button><p className="eyebrow">THE CASE</p><h2>The Puppeteer returns</h2><p>Eighteen months after his family was murdered, Detective Aarav Mehra receives a new threat. Psychologist Dr. Rishabh Malhotra has been found poisoned, and the killer promises three more deaths in three days.</p><p>Explore the first case and keep evidence separate from suspicion.</p><button className="btn primary" onClick={() => navigate("login")}>Enter the case →</button></section></div>}
  </main>;
}

function Login({ navigate, setUser }) {
  const [name, setName] = useState("");
  return <main className="login-page"><button className="text-button upper-back" onClick={() => navigate("landing")}>← Back to home</button><div className="login-layout"><section className="login-card"><p className="eyebrow">RED THREAD / PLAYER ACCESS</p><h2>Login</h2><p className="muted">Enter your detective name to play the offline preview.</p><form onSubmit={e => { e.preventDefault(); setUser({name:name.trim(),mode:"guest"});navigate("cases"); }}><label htmlFor="detective-name">Detective name</label><input id="detective-name" placeholder="Your name" value={name} onChange={e=>setName(e.target.value)} maxLength={50} required/><button className="btn primary full" type="submit">Enter preview</button></form><div className="divider"><span>OR</span></div><GoogleSignIn done={u => { setUser(u); navigate("cases"); }}/><button className="text-button guest-link" onClick={() => { setUser({name:"Guest Detective",mode:"guest"});navigate("cases"); }}>Continue as guest →</button><p className="fine-print">Preview names are local only. Google login needs your OAuth client ID. No password is collected.</p></section></div></main>;
}

function Cases({ navigate, progress }) {
  return <main className="case-select"><header className="simple-header"><button className="text-button" onClick={() => navigate("login")}>←</button><h1>Select a Case</h1><span aria-hidden="true">⚙</span></header><div className="case-list"><article className="case-choice"><img src={import.meta.env.BASE_URL + "crime-study.png"} alt="Rishabh Malhotra's study at night, with a chessboard"/><div className="case-choice-body"><p className="eyebrow">DAY 1 / CASE 001</p><h2>{caseFile.title}</h2><p>The Last Three Days · {progress.found.length}/10 clues collected</p><button className="btn primary" onClick={() => navigate("game")}>Start Case &nbsp; →</button></div></article><article className="future-card"><img src={import.meta.env.BASE_URL + "crime-study.png"} alt="" /><div><span>🔒</span><h3>The Forgotten</h3><p>Day 2 · Coming later</p></div></article><article className="future-card"><img src={import.meta.env.BASE_URL + "crime-study.png"} alt="" /><div><span>🔒</span><h3>The Final Move</h3><p>Day 3 · Coming later</p></div></article></div></main>;
}

function App() {
  const [screen, navigate] = useState("landing");
  const [user, setUser] = useState(null);
  const [progress, setProgress] = useState(loadProgress);
  useEffect(() => { try { localStorage.setItem(KEY, JSON.stringify(progress)); } catch { /* Optional local save. */ } }, [progress]);
  if (screen === "landing") return <Landing navigate={navigate}/>;
  if (screen === "login") return <Login navigate={navigate} setUser={setUser}/>;
  if (screen === "cases") return <Cases navigate={navigate} progress={progress}/>;
  return <Game navigate={navigate} user={user} setUser={setUser} progress={progress} setProgress={setProgress}/>;
}

createRoot(document.getElementById("root")).render(<App/>);
