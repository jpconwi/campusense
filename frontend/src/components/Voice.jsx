/*
 * Voice.jsx - speak instead of type.
 *
 * The browser turns speech into text (Web Speech API: Chrome, Edge, Safari, Android Chrome).
 * The words go into the normal text box, so the student can read and correct them before
 * anything is sent. Nothing is recorded or stored by NEMSAI. In browsers without speech
 * recognition (for example Firefox) the button is hidden and typing works as before.
 * Note: Chrome sends the audio to Google's speech service to do the recognition.
 */
import { useEffect, useRef, useState } from "react";

const Recognition = typeof window !== "undefined"
  ? window.SpeechRecognition || window.webkitSpeechRecognition : null;

export const voiceSupported = () => Boolean(Recognition);

const LANG = "en-PH";

const ERRORS = {
  "not-allowed": "Microphone access is blocked. Allow the microphone in your browser settings, or type instead.",
  "service-not-allowed": "Microphone access is blocked. Allow the microphone in your browser settings, or type instead.",
  "audio-capture": "No microphone was found.",
  "network": "Voice input needs an internet connection.",
  "language-not-supported": "That language is not supported for voice input here.",
};

/** value / onChange work like a normal controlled text box. */
export function useVoice(value, onChange) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState("");
  const rec = useRef(null);
  const base = useRef("");
  const latest = useRef({ value, onChange });
  latest.current = { value, onChange };

  function stop() { if (rec.current) rec.current.stop(); }

  function start() {
    if (!Recognition) return;
    setError("");
    const r = new Recognition();
    r.lang = LANG;
    r.continuous = true;
    r.interimResults = true;
    base.current = latest.current.value ? latest.current.value.replace(/\s+$/, "") + " " : "";
    r.onresult = (event) => {
      let said = "";
      for (let i = 0; i < event.results.length; i++) said += event.results[i][0].transcript;
      latest.current.onChange((base.current + said.trim()).slice(0, 2000));
    };
    r.onerror = (event) => {
      if (event.error !== "no-speech" && event.error !== "aborted") setError(ERRORS[event.error] || "Voice input stopped. Please try again or type.");
    };
    r.onend = () => { setListening(false); rec.current = null; };
    try { r.start(); rec.current = r; setListening(true); } catch { setError("Could not start the microphone."); }
  }

  useEffect(() => () => { if (rec.current) rec.current.abort(); }, []);
  return { supported: voiceSupported(), listening, error, toggle: () => (listening ? stop() : start()) };
}

/** Mic button (+ language picker + status). Renders nothing when the browser cannot do it. */
export default function MicButton({ value, onChange, disabled, compact }) {
  const v = useVoice(value, onChange);
  if (!v.supported) return null;
  return (
    <span className={"mic-wrap" + (compact ? " compact" : "")}>
      <button type="button" className={"mic-btn" + (v.listening ? " on" : "")} disabled={disabled}
              aria-pressed={v.listening} aria-label={v.listening ? "Stop voice input" : "Speak your message"}
              title={v.listening ? "Stop" : "Speak instead of typing"} onClick={v.toggle}>
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
        </svg>
      </button>
      {v.listening && <span className="mic-status" role="status">Listening… tap the mic to stop, then fix any mistakes.</span>}
      {v.error && <span className="mic-error" role="alert">{v.error}</span>}
    </span>
  );
}
