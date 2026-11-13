export const caseFile = {
  id: "CASE 001", title: "The Silent Witness", series: "The Last Three Days",
  victim: "Dr. Rishabh Malhotra", location: "Blackwood Residency · 17th floor",
  summary: "A psychologist is found poisoned beside an unfinished chess game. The Puppeteer has returned with a warning: three people, three days.",
};
const asset = (name) => import.meta.env.BASE_URL + name;

// All dialogue here is authored frontend sample copy, never generated AI or canonically verified testimony.
export const suspects = [
  { id: "anaya", name: "Anaya Kapoor", role: "Musician · former partner of the killer", portrait: asset("anaya.png"), intro: "I knew Rishabh. That doesn't mean I was there that night.", questions: [
    ["When did you last meet Rishabh?", "I last met Rishabh two weeks ago. That is what I told the investigators."],
    ["How do you recognize people?", "Footsteps. Some people have a rhythm you don't forget."],
    ["Do you know his apartment?", "I know its layout. I understand why that sounds strange."],
    ["Have you received letters?", "Anonymous letters have been arriving for months. I kept them."],
  ] },
  { id: "kabir", name: "Kabir Malhotra", role: "Entrepreneur · victim's brother", portrait: asset("kabir.png"), intro: "My brother and I argued. We were still family.", questions: [
    ["Where were you that night?", "At a business dinner. You can check the people who attended."],
    ["Why are your prints on the board?", "I have been in that apartment before. Prints don't tell you when I touched it."],
    ["What was the financial dispute?", "We disagreed over the inheritance. I won't pretend otherwise."],
    ["What about the transfer?", "That account is my business. I know how this looks."],
  ] },
  { id: "nisha", name: "Dr. Nisha Verma", role: "Psychiatrist · research associate", portrait: asset("nisha.png"), intro: "Rishabh was frightened. I wish he had told me more.", questions: [
    ["Did you visit Rishabh?", "Yes. I visited him that evening. We discussed our work."],
    ["What is Project Echo?", "It was confidential research. I can't explain the missing file."],
    ["Did you have access to medication?", "I work in psychiatry. Access is not evidence that I poisoned anyone."],
    ["What did Rishabh fear?", "He said someone was watching him, but he would not give me a name."],
  ] },
];

export const clues = [
  { id: "01", name: "The Chessboard", type: "Crime scene", icon: "♞", summary: "15 pieces remain; the black king is missing.", detail: "The victim held a white chess piece. The board's position suggests a skilled player, but it does not prove a real game took place." },
  { id: "02", name: "The Broken Watch", type: "Object", icon: "◷", summary: "The watch stopped at 9:17 PM.", detail: "It is internally damaged. The stopped time cannot be assumed to be the time of death." },
  { id: "03", name: "The Audio Recording", type: "Digital", icon: "♫", summary: "A 17-second clip with two voices and three chimes.", detail: "The speakers and recording location are unconfirmed. The clock chimes may help establish an independent timeline." },
  { id: "04", name: "The Coffee Cups", type: "Forensics", icon: "☕", summary: "Two cups; poison found in one.", detail: "Only one cup has Rishabh's fingerprints. This does not yet establish who prepared or handled either drink." },
  { id: "05", name: "The Elevator Footage", type: "Video", icon: "▣", summary: "Three visitors entered the apartment floor.", detail: "One visitor's face is not captured. Their identity and exact movements remain uncertain." },
  { id: "06", name: "Anaya's Statement", type: "Testimony", icon: "◉", summary: "She says she heard an argument at 9:40 PM.", detail: "She says she recognized the other person's footsteps. This is her account, not independently verified fact." },
  { id: "07", name: "The Missing Research File", type: "Digital", icon: "▤", summary: "A document called Project Echo is missing.", detail: "The last access was three hours before Rishabh died. Whether it was removed, copied, or destroyed is unknown." },
  { id: "08", name: "The Photograph", type: "Object", icon: "▧", summary: "Four people pictured seven years earlier.", detail: "Rishabh, Anaya, Nisha, and an unidentified man appear together. The man's identity is unknown." },
  { id: "09", name: "The Unsent Message", type: "Digital", icon: "✉", summary: "A draft mentions Tara and another person.", detail: "The draft reads: ‘I know what happened to Tara. He wasn't alone that night.’ It was never sent; its claim is unverified." },
  { id: "10", name: "The Red Thread", type: "Forensics", icon: "〰", summary: "Thread beneath the victim's fingernail.", detail: "It matches neither the victim's clothes nor visible clothing of the three suspects. Its origin is unknown." },
];

export const initialProgress = { found: ["01"], notes: "", interviews: {}, links: [], theory: null };
