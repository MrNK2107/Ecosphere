/**
 * TTS helper — Agent E.
 * POST /incidents/{id}/summary -> markdown + ttsScript, then speak via Web Speech API
 * or play audio if backend returns TTS url.
 */

const API_ENV = (import.meta as unknown as { env: Record<string,string> }).env?.VITE_API_URL ?? "";

function apiBase(): string {
  if (API_ENV) return API_ENV.replace(/\/$/, "");
  if (typeof window !== "undefined" && window.location.port === "5173") return "/api";
  return "http://localhost:8000";
}

export type SummaryResponse = {
  incidentId: string;
  markdown: string;
  ttsScript?: string;
  ttsUrl?: string;
  audioUrl?: string;
};

let currentUtterance: SpeechSynthesisUtterance | null = null;

export async function fetchSummary(incidentId: string): Promise<SummaryResponse> {
  const base = apiBase();
  const r = await fetch(`${base}/incidents/${incidentId}/summary`, { method: "POST" });
  if (!r.ok) throw new Error(`summary ${r.status}: ${await r.text()}`);
  const j = await r.json();
  // API returns { incidentId, markdown } plus maybe ttsScript/ttsUrl
  // Synthesize ttsScript locally if not provided: strip markdown
  if (!j.ttsScript && j.markdown) {
    const plain = j.markdown.replace(/^#.*$/gm, "").replace(/[*_`\[\]]/g, "").replace(/\n{2,}/g, "\n").slice(0, 800);
    j.ttsScript = plain.split("\n").filter(Boolean).slice(0, 6).join(". ").slice(0, 800);
  }
  return j as SummaryResponse;
}

export function speakWithWebSpeech(text: string, voiceHint?: string): SpeechSynthesisUtterance {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    throw new Error("Web Speech API not available");
  }
  // cancel previous
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text.slice(0, 800));
  u.rate = 1;
  u.pitch = 1;
  u.volume = 1;
  if (voiceHint) {
    const voices = window.speechSynthesis.getVoices();
    const match = voices.find((v) => v.name.toLowerCase().includes(voiceHint.toLowerCase()));
    if (match) u.voice = match;
  }
  currentUtterance = u;
  window.speechSynthesis.speak(u);
  return u;
}

export function stopSpeaking(): void {
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
  currentUtterance = null;
  const audio = document.getElementById("tts-audio") as HTMLAudioElement | null;
  if (audio) {
    audio.pause();
    audio.src = "";
  }
}

export async function speakSummary(incidentId: string): Promise<SummaryResponse> {
  const res = await fetchSummary(incidentId);
  // If backend provided audio url, play it; otherwise Web Speech
  const audioUrl = (res as unknown as Record<string,string>).ttsUrl ?? (res as unknown as Record<string,string>).audioUrl;
  if (audioUrl) {
    let audio = document.getElementById("tts-audio") as HTMLAudioElement | null;
    if (!audio) {
      audio = document.createElement("audio");
      audio.id = "tts-audio";
      audio.controls = true;
      audio.autoplay = true;
      document.body.appendChild(audio);
    }
    audio.src = audioUrl;
    try { await audio.play(); } catch { /* autoplay blocked */ }
    return res;
  }
  const script = res.ttsScript ?? res.markdown.replace(/[#*`]/g, "").slice(0, 800);
  try {
    speakWithWebSpeech(script);
  } catch (e) {
    console.warn("TTS Web Speech failed", e);
  }
  return res;
}

export function isSpeaking(): boolean {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return false;
  return window.speechSynthesis.speaking;
}
