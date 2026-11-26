// Presentation-only mappings. All case content comes from the backend API.
const portraits = { suspect_001: "anaya.png", suspect_002: "kabir.png", suspect_003: "nisha.png" };
const clueIcons = ["♞", "◷", "♫", "☕", "▣", "◉", "▤", "▧", "✉", "〰"];

export function presentSuspect(suspect) {
  // Adapts one item returned by GET /cases/{case_id}/suspects to the existing
  // component field names. Portraits/icons are presentation assets, not case data.
  return {
    id: suspect.suspect_id,
    name: suspect.name,
    role: [suspect.occupation, suspect.relationship_to_victim].filter(Boolean).join(" · "),
    portrait: import.meta.env.BASE_URL + (portraits[suspect.suspect_id] || "detective-office.png"),
    intro: suspect.public_description,
    questions: [
      "What was your relationship with the victim?",
      "Where were you on the night of the murder?",
      "Is there anything you have not told the investigators?",
    ],
  };
}

export function presentClue(clue, index = 0) {
  // Adapts clue summaries/details returned by GET /sessions/{id}/evidence.
  return {
    id: clue.clue_id,
    name: clue.title,
    type: clue.clue_type.replaceAll("_", " "),
    icon: clueIcons[index % clueIcons.length],
    summary: clue.source,
    detail: clue.description || clue.source,
  };
}

export const initialProgress = { notes: "", links: [], theory: null };
