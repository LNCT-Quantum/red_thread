import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import React from "react";
import { renderToString } from "react-dom/server";
import { createServer } from "vite";

const server = await createServer({ server: { middlewareMode: true }, appType: "custom" });
try {
  const [{ default: Game }, story] = await Promise.all([
    server.ssrLoadModule("/src/Game.jsx"),
    server.ssrLoadModule("/src/story.js"),
  ]);
  const html = renderToString(React.createElement(Game, {
    caseInfo: { case_id: "case_001", title: "API case" },
    initialSection: "overview", goHome() {}, setProgress() {}, progress: story.initialProgress,
  }));
  assert.ok(html.includes("Loading investigation"));
  assert.equal(typeof story.presentSuspect, "function");
  assert.equal(typeof story.presentClue, "function");
  const source = readFileSync(new URL("../src/Game.jsx", import.meta.url), "utf8");
  for (const route of ["/dialogue", "/evidence", "/history", "/complete"]) assert.ok(source.includes(route), `missing API route ${route}`);
  assert.ok(!source.includes("scripted preview"));
  for (const file of ["detective-office.png", "crime-study.png", "anaya.png", "kabir.png", "nisha.png"]) assert.ok(existsSync(new URL("../public/" + file, import.meta.url)), file + " missing");
  console.log("PASS API-driven game shell and image assets");
} finally { await server.close(); }
