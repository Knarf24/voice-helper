// Page code: microphone, speaking, conversation log. Understanding and answering is done in Python (helper.py).
const $ = (id) => document.getElementById(id);

let py = null, answerJson = null;
let languages = [];
let busy = false;
let listening = false;
let recognizer = null;

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const synth = window.speechSynthesis;

// ---------- start-up ----------
async function startPython() {
  py = await loadPyodide({ indexURL: new URL("pyodide/", location.href).href });
  $("loadText").textContent = "Loading the helper…";
  const code = await fetch("helper.py").then((r) => { if (!r.ok) throw new Error("helper.py missing"); return r.text(); });
  py.FS.writeFile("/home/pyodide/helper.py", code);
  py.runPython("import helper");
  const helper = py.pyimport("helper");
  answerJson = helper.answer_json;
  languages = JSON.parse(helper.languages_json());
}

function fillLanguages() {
  const sel = $("lang");
  sel.innerHTML = "";
  for (const l of languages) {
    const o = document.createElement("option");
    o.value = l.code;
    o.textContent = l.native === l.name ? l.name : `${l.native} (${l.name})`;
    sel.appendChild(o);
  }
  let saved = null;
  try { saved = localStorage.getItem("vh-lang"); } catch (e) { /* private mode */ }
  const fromUrl = new URLSearchParams(location.search).get("lang");
  const browser = (navigator.language || "en").slice(0, 2);
  sel.value = [fromUrl, saved, browser, "en"].find((c) => c && languages.some((l) => l.code === c));
}

const langInfo = (code) => languages.find((l) => l.code === code) || languages[0];

function setLanguage(code) {
  $("lang").value = code;
  try { localStorage.setItem("vh-lang", code); } catch (e) { /* ignore */ }
  updateVoiceNote();
}

// ---------- speaking ----------
function voiceFor(code) {
  if (!synth) return null;
  const voices = synth.getVoices();
  const tag = langInfo(code).tag.toLowerCase();
  const norm = (v) => v.lang.replace("_", "-").toLowerCase();
  return voices.find((v) => norm(v) === tag) || voices.find((v) => norm(v).split("-")[0] === code) || null;
}

function canSpeak(code) {
  // English always has a voice; for other languages only speak if a matching voice is installed
  // (otherwise an English voice would mispronounce the words).
  return !!synth && (code === "en" || !!voiceFor(code));
}

function updateVoiceNote() {
  const code = $("lang").value;
  const notes = [];
  if (!Recognition) notes.push("This browser can't listen; please type.");
  if (!synth) notes.push("This browser can't read aloud.");
  else if (synth.getVoices().length && !canSpeak(code)) notes.push(`No ${langInfo(code).name} voice on this device, so answers are shown as text.`);
  $("voiceNote").textContent = notes.join(" ");
}

function speak(parts) {
  if (!synth || !$("speakOn").checked) return;
  synth.cancel();
  for (const p of parts) {
    if (!p.text || !canSpeak(p.lang)) continue;
    const u = new SpeechSynthesisUtterance(p.text);
    u.lang = langInfo(p.lang).tag;
    const v = voiceFor(p.lang);
    if (v) u.voice = v;
    u.rate = parseFloat($("rate").value);
    synth.speak(u);
  }
}

// ---------- conversation log ----------
function addMessage(cls, html) {
  const log = $("log");
  log.querySelector(".empty")?.remove();
  const div = document.createElement("div");
  div.className = "msg " + cls;
  div.innerHTML = html;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function showAnswer(bubble, res) {
  const [main, ...extra] = res.say;
  let html = esc(main?.text || "");
  for (const e of extra) html += `<span class="said" lang="${esc(e.tag)}">${esc(e.text)}</span>`;
  const meta = [];
  meta.push(`<button type="button" class="again">🔊 Say again</button>`);
  if (res.source) {
    const host = new URL(res.source).hostname.replace(/^www\./, "");
    meta.push(`<a href="${esc(res.source)}" target="_blank" rel="noopener">Source: ${esc(host)}</a>`);
  }
  const mute = res.say.filter((p) => !canSpeak(p.lang)).map((p) => langInfo(p.lang).name);
  if (mute.length) meta.push(`<span>No ${esc([...new Set(mute)].join(" or "))} voice on this device</span>`);
  bubble.classList.remove("typing");
  bubble.classList.toggle("err", !!res.error);
  bubble.innerHTML = html + `<div class="meta">${meta.join("")}</div>`;
  bubble.querySelector(".again").onclick = () => speak(res.say);
  bubble.lang = langInfo(main?.lang || "en").tag;
}

function localIso() {
  const d = new Date(), p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

async function ask(question) {
  question = question.trim();
  if (!question || busy || !answerJson) return;
  busy = true; setBusy(true);
  const lang = $("lang").value;
  const me = addMessage("me", esc(question));
  me.lang = langInfo(lang).tag;
  const bot = addMessage("bot typing", "Thinking…");
  try {
    const res = JSON.parse(await answerJson(question, lang, localIso()));
    if (lang !== "en" && res.heard_en && res.heard_en.toLowerCase() !== question.toLowerCase()) {
      me.insertAdjacentHTML("beforeend", `<span class="sub">English: ${esc(res.heard_en)}</span>`);
    }
    if (res.set_lang) setLanguage(res.set_lang);
    showAnswer(bot, res);
    speak(res.say);
  } catch (e) {
    console.error(e);
    showAnswer(bot, { say: [{ text: "Sorry, something went wrong: " + e.message, lang: "en" }], error: String(e) });
  } finally {
    busy = false; setBusy(false);
  }
}

function setBusy(on) {
  $("mic").classList.toggle("busy", on);
  $("mic").disabled = on || !Recognition;
  $("send").disabled = on;
  $("micText").textContent = on ? "Finding the answer…" : Recognition ? "Tap the microphone and ask a question" : "Type your question below";
}

// ---------- listening ----------
function toggleListening() {
  if (listening) { recognizer?.stop(); return; }
  if (!Recognition || busy) return;
  synth?.cancel();
  recognizer = new Recognition();
  recognizer.lang = langInfo($("lang").value).tag;
  recognizer.interimResults = true;
  recognizer.maxAlternatives = 1;
  recognizer.continuous = false;
  let finalText = "";
  recognizer.onstart = () => {
    listening = true;
    $("mic").classList.add("listening");
    $("micText").textContent = `Listening in ${langInfo($("lang").value).name}… (tap to stop)`;
    $("interim").textContent = "";
  };
  recognizer.onresult = (ev) => {
    let interim = "";
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      if (ev.results[i].isFinal) finalText += ev.results[i][0].transcript;
      else interim += ev.results[i][0].transcript;
    }
    $("interim").textContent = finalText + interim;
  };
  recognizer.onerror = (ev) => {
    const why = {
      "not-allowed": "Microphone permission was refused. Allow it in the address bar, or type instead.",
      "service-not-allowed": "Microphone permission was refused. Allow it in the address bar, or type instead.",
      "no-speech": "I didn't hear anything. Tap and try again.",
      "language-not-supported": `This browser can't listen in ${langInfo($("lang").value).name}. Please type instead.`,
      "network": "Speech recognition needs an internet connection.",
      "audio-capture": "No microphone was found.",
    }[ev.error];
    if (why) $("interim").textContent = why;
  };
  recognizer.onend = () => {
    listening = false;
    $("mic").classList.remove("listening");
    if (!busy) setBusy(false);
    if (finalText.trim()) { $("interim").textContent = ""; ask(finalText); }
  };
  try { recognizer.start(); } catch (e) { $("interim").textContent = e.message; }
}

// ---------- wiring ----------
function wire() {
  $("mic").onclick = toggleListening;
  $("typeForm").onsubmit = (e) => { e.preventDefault(); const q = $("typed").value; $("typed").value = ""; ask(q); };
  $("lang").onchange = () => setLanguage($("lang").value);
  $("stop").onclick = () => { synth?.cancel(); recognizer?.abort(); };
  $("clear").onclick = () => { synth?.cancel(); $("log").innerHTML = '<p class="empty small">Your questions and the helper\'s answers appear here.</p>'; };
  for (const chip of document.querySelectorAll(".chip")) {
    chip.onclick = () => { if (chip.dataset.lang) setLanguage(chip.dataset.lang); ask(chip.dataset.q); };
  }
  if (synth) synth.onvoiceschanged = updateVoiceNote;
  $("speakOn").onchange = () => { if (!$("speakOn").checked) synth?.cancel(); };
}

(async () => {
  wire();
  try {
    await startPython();
    fillLanguages();
    updateVoiceNote();
    for (const el of ["lang", "typed", "send"]) $(el).disabled = false;
    setBusy(false);
    $("loading").hidden = true;
    const q = new URLSearchParams(location.search).get("q");
    if (q) ask(q);
  } catch (e) {
    console.error(e);
    $("loading").classList.add("error");
    $("loadText").textContent = "Couldn't start Python: " + e.message + ". Please reload the page.";
    document.querySelector(".spinner")?.remove();
  }
})();
