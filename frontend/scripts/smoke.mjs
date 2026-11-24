import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import React from "react";
import { renderToString } from "react-dom/server";
import { createServer } from "vite";

const server = await createServer({ server: { middlewareMode: true }, appType: "custom" });
try {
  const [{ default: Game }, story] = await Promise.all([
    server.ssrLoadModule("/src/Game.jsx"),
    server.ssrLoadModule("/src/story.js"),
  ]);
  const progress = structuredClone(story.initialProgress);
  const sections = [
    ["overview", "The Silent Witness"], ["suspects", "Anaya Kapoor"],
    ["interview", "Ask another question"], ["evidence", "The Chessboard"],
    ["timeline", "9:17 PM"], ["notes", "My notes"], ["theory", "There is no verdict yet"],
  ];
  for (const [section, expected] of sections) {
    const html = renderToString(React.createElement(Game, {
      initialSection: section, goHome() {}, setProgress() {}, progress,
    }));
    assert.ok(html.includes(expected), section + " should render " + expected);
    assert.ok(!html.includes("Sign out"), section + " should not show authentication controls");
    console.log("PASS", section);
  }
  assert.equal(story.suspects.length, 3);
  assert.equal(story.clues.length, 10);
  for (const file of ["detective-office.png", "crime-study.png", "anaya.png", "kabir.png", "nisha.png"]) {
    assert.ok(existsSync(new URL("../public/" + file, import.meta.url)), file + " missing");
  }
  console.log("PASS story data and image assets");
} finally {
  await server.close();
}
