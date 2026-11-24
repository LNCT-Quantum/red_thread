# Red Thread — The Last Three Days

Standalone React/Vite frontend for **Case 001: The Silent Witness**. The app now follows a direct flow: landing page → game dashboard → NPC interviews, evidence, timeline, notes, and case theory. No account, login, or external identity provider is required.

## Run

**Windows:** open the `frontend` folder and double-click `start-windows.bat`. It installs dependencies if needed, starts Vite, and opens the landing page. Keep its server window open. Node.js 20.19+ or 22.12+ must already be installed.

**Terminal (Windows/macOS/Linux):**

```sh
npm ci
npm run dev
```

Open the local URL printed by Vite, usually `http://localhost:5173`. Do not double-click `index.html`; the Vite app must be served.

Build and test with:

```sh
npm run test:smoke
npm run build
```

The production files are generated in `dist/` and use relative asset paths for subpath hosting.

## What works in the preview

- Clicking **Start Game** on the landing page opens the investigation dashboard immediately.
- The suspects are Anaya Kapoor, Kabir Malhotra, and Dr. Nisha Verma.
- Prepared questions return scripted sample responses; custom questions receive a safe preview response.
- The first clue starts available and the remaining nine are revealed in story order.
- Notes, interviews, clues, links, and the current theory persist in this browser under `red-thread-demo-v2`.
- The 72-hour indicator is a story label rather than a ticking timer.
- Connections and theories are player hypotheses; this preview does not declare an official culprit.

## Integration boundary

Replace scripted interviews and local case data with the game manager API when backend integration is ready. The backend should own NPC knowledge, authorized clues, authoritative state, timeline, and accusation grading. The current frontend is a local story preview.
