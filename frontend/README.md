# Red Thread — The Last Three Days

Standalone React/Vite frontend for **Case 001: The Silent Witness**, based on the supplied story. Its screen flow follows the supplied UI reference: landing → login → case selection → dashboard → NPC selection → interrogation → evidence → notes → case theory. It also includes a timeline. The landing and case scenes and three portraits are bundled local images.

## Run

**Windows:** extract the ZIP, open the `frontend` folder, and double-click `start-windows.bat`. It installs dependencies if needed, starts Vite, and opens the landing page. Keep its server window open. Node.js 20.19+ or 22.12+ must already be installed.

**Terminal (Windows/macOS/Linux):**

```sh
npm ci
npm run dev
```

Open the local URL printed by Vite (usually `http://localhost:5173`). **Do not double-click `index.html`**; a Vite app must be served. Build with `npm run build`; the deployable files are in `dist/` and use relative asset paths for subpath hosting. The preview works without a backend or OAuth setup.

Run `npm run test:smoke` to render and check every investigation screen, story data, and image references.

## Set up Google sign-in

This uses the official Google Identity Services **browser OAuth token client** with `openid email profile`; the returned access token is used once to fetch the user's Google profile. To activate:

1. Create a Google Cloud OAuth **Web application** client ID and configure the consent screen.
2. Add the exact development origin (for example `http://127.0.0.1:5173` for the Windows launcher, and/or `http://localhost:5173`) and deployed origin to **Authorized JavaScript origins**. The scheme, host, and port must match the browser address.
3. Copy `.env.example` to `.env` and set the public ID: `VITE_GOOGLE_CLIENT_ID=your-id.apps.googleusercontent.com`. Restart Vite.
4. Serve the deployed site over HTTPS. Do not put a client secret into this frontend.

If a client ID is absent, the button explains why and local preview access remains available. A real Google account login cannot work with an unregistered origin or a blank client ID. This browser-only identity has no backend session; **do not treat local state or the displayed Google profile as server-verified authorization**. A backend integration must verify identity and enforce case access.

Google setup: https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid
Browser token flow: https://developers.google.com/identity/oauth2/web/guides/use-token-model

## What works in the preview

- The suspects are Anaya Kapoor, Kabir Malhotra, and Dr. Nisha Verma. Prepared questions return **scripted sample responses**; custom questions receive a safe preview response, not generated AI.
- The first clue starts available. “Search for next clue” progressively reveals the remaining nine in story order. This is a linear UI demo, not real evidence retrieval.
- Notes, interviews, clues, links, and current theory persist in this browser's `localStorage` under `red-thread-demo`. They are **not synced between devices or accounts**. Clearing browser data resets them.
- The “72 hours” indicator is a **story label**, not a ticking timer. Day 2 and Day 3 are future chapters.
- Connections and theories are player hypotheses. There is no “Solved” verdict: the supplied story leaves the canonical culprit, minute-by-minute timeline, clue classifications, and ending undefined.

## Integration boundary

Replace scripted interviews and local case data with the game manager API. Display only its final validated dialogue response (or safe fallback), never an unvalidated draft. The backend must own NPC knowledge, authorized/revealed clues, login/session validation, authoritative state, timeline, and accusation grading. The current frontend does **not** claim AI safety or story correctness.
