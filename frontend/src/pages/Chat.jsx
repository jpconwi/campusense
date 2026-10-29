/* Chat.jsx - the NEMSAI chat window. */
import { Fragment, useEffect, useRef, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import PhotoReportCard from "../components/PhotoReportCard.jsx";
import RecordForm, { SuccessCard } from "../components/RecordForm.jsx";
import MicButton from "../components/Voice.jsx";
import { ChatSkeleton, ReplySkeleton } from "../components/Skeletons.jsx";

const FORM_TYPES = {
  concern_form: "concern", report_form: "report", feedback_form: "feedback",
  reservation_form: "reservation", faculty_form: "faculty",
};

const MAX_PHOTO_MB = 5;
const PHOTO_TYPES = ["image/png", "image/jpeg", "image/webp"];

const timeNow = () => new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

// ---------- Markdown (safe: React escapes every piece of text) ----------
// Web addresses in an answer become real links (only http/https, so nothing unsafe can run).
const URL_RE = /(https?:\/\/[^\s<>"]*[^\s<>".,;:!?)\]'])/g;

function linkLabel(url) {
  try {
    const u = new URL(url);
    if (u.hostname.endsWith("nemsu.edu.ph") && u.pathname.startsWith("/news/")) return "Read the full article \u2197";
    return u.hostname + (u.pathname.length > 1 ? "/\u2026" : "");
  } catch {
    return url;
  }
}

function Linked({ text }) {
  return text.split(URL_RE).map((part, i) =>
    /^https?:\/\//.test(part)
      ? <a key={i} href={part} target="_blank" rel="noopener noreferrer">{linkLabel(part)}</a>
      : <Fragment key={i}>{part}</Fragment>);
}

function Inline({ text }) {
  return text.split(/(\*\*.+?\*\*)/g).map((part, i) =>
    /^\*\*.+\*\*$/.test(part) ? <strong key={i}>{part.slice(2, -2)}</strong> : <Linked key={i} text={part} />);
}

function Markdown({ text }) {
  const blocks = [];
  let para = [], list = null;
  const flushPara = () => {
    if (para.length) {
      blocks.push(<p key={blocks.length}>{para.map((l, i) => <Fragment key={i}>{i > 0 && <br />}<Inline text={l} /></Fragment>)}</p>);
      para = [];
    }
  };
  const closeList = () => {
    if (list) {
      const items = list.items.map((t, i) => <li key={i}><Inline text={t} /></li>);
      blocks.push(list.type === "ol" ? <ol key={blocks.length} start={list.start}>{items}</ol> : <ul key={blocks.length}>{items}</ul>);
      list = null;
    }
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const ol = line.match(/^(\d+)\.\s+(.*)/);
    const ul = line.match(/^[-*]\s+(.*)/);
    if (ol || ul) {
      flushPara();
      const type = ol ? "ol" : "ul";
      if (!list || list.type !== type) { closeList(); list = { type, start: ol ? ol[1] : undefined, items: [] }; }
      list.items.push(ol ? ol[2] : ul[1]);
    } else if (line === "") { flushPara(); closeList(); }
    else { closeList(); para.push(line); }
  }
  flushPara(); closeList();
  return <>{blocks}</>;
}

// ---------- map card (Google Maps, shown when the user asks where the campus is) ----------
function MapCard({ map }) {
  return (
    <div className="map-card">
      <iframe
        title={map.title}
        src={map.embed_url}
        loading="lazy"
        allowFullScreen
        referrerPolicy="no-referrer-when-downgrade"
      />
      <div className="map-card-foot">
        <strong>{map.title}</strong>
        <a href={map.url} target="_blank" rel="noopener noreferrer">Open in Google Maps</a>
      </div>
    </div>
  );
}

// ---------- one row in the conversation ----------
function Row({ item, onSuggest }) {
  const ai = item.role === "ai";
  return (
    <div className={"message " + item.role}>
      {ai && <img className="avatar" src="/logo.png" alt="" />}
      <div className="stack">
        {item.kind === "typing" && (
          <div className="bubble rich"><ReplySkeleton /></div>
        )}
        {item.kind === "text" && (
          <div className={"bubble" + (item.error ? " error" : "") + (ai && !item.error ? " rich" : "")}>
            {item.image && <img className="sent-photo" src={item.image} alt="Photo you sent" />}
            {ai && !item.error ? <Markdown text={item.text} /> : item.text}
          </div>
        )}
        {item.kind === "text" && item.suggestions && item.suggestions.length > 0 && (
          <div className="chips-row" style={{ flexWrap: "wrap" }}>
            {item.suggestions.map((q) => (
              <button key={q} className="chip" type="button" onClick={() => onSuggest(q)}>{q}</button>
            ))}
          </div>
        )}
        {item.kind === "form" && (
          <div className="bubble rich">
            <RecordForm kind={item.formKind} prefill={item.prefill} onSuccess={item.onSuccess} />
          </div>
        )}
        {item.kind === "photo" && (
          <PhotoReportCard result={item.result} preview={item.preview}
                           onMessage={item.onMessage} onSent={item.onSent} onDiscarded={item.onDiscarded} />
        )}
        {item.kind === "map" && <MapCard map={item.map} />}
        {item.kind === "note" && <div className="bubble rich"><em>{item.text}</em></div>}
        {item.kind === "success" && <SuccessCard result={item.result} />}
        {(item.kind === "text") && <div className="time">{item.time}</div>}
      </div>
    </div>
  );
}

// turn the saved messages of an old chat back into rows
function restore(messages) {
  const rows = [];
  let id = 1;
  const push = (item) => rows.push({ id: id++, ...item });
  for (const m of messages) {
    const time = new Date(m.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    if (m.role === "user") { push({ role: "user", kind: "text", text: m.text, time }); continue; }
    push({ role: "ai", kind: "text", text: m.text, suggestions: m.suggestions, time });
    if (m.type === "map" && m.map) push({ role: "ai", kind: "map", map: m.map });
    if (FORM_TYPES[m.type]) push({ role: "ai", kind: "note", text: "A form was shown here. Ask again to open a new one." });
  }
  return { rows, next: id };
}

const QUICK = [
  "What equipment can I borrow?",
  "How do I report a broken facility?", "Where is the NEMSU Tandag campus?", "Where is the library?",
  "Which canteen is near the CBM area?",
];
const RESERVE_QUICK = "How do I reserve a room or facility?";   // instructors only

export default function Chat() {
  const { user } = useAuth();
  const { chatKey, openId, onSaved } = useOutletContext();
  const [items, setItems] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingChat, setLoadingChat] = useState(false);   // an old chat is being opened
  const bottom = useRef(null);
  const input = useRef(null);
  const nextId = useRef(1);
  const sessionId = useRef(null);                      // the saved chat we are talking in
  const [photo, setPhoto] = useState(null);            // { file, url } waiting to be sent
  const [menuOpen, setMenuOpen] = useState(false);
  const [photoError, setPhotoError] = useState("");
  const cameraInput = useRef(null);
  const galleryInput = useRef(null);

  useEffect(() => { document.title = "Campus AI | NEMSU"; }, []);
  useEffect(() => {                                    // "New chat" or a chat picked from the history
    let alive = true;
    setItems([]); setText(""); sessionId.current = null; nextId.current = 1;
    setLoadingChat(!!openId);
    if (openId) {
      api(`/api/chats/${openId}`).then((d) => {
        if (!alive) return;
        const { rows, next } = restore(d.messages);
        sessionId.current = d.id; nextId.current = next; setItems(rows);
      }).catch(() => { if (alive) onSaved(); })        // deleted meanwhile: just refresh the list
        .finally(() => { if (alive) setLoadingChat(false); });
    }
    input.current && input.current.focus();
    return () => { alive = false; };
  }, [chatKey]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { bottom.current && bottom.current.scrollIntoView({ block: "end" }); }, [items]);
  useEffect(() => {                                    // grow the box while typing
    const el = input.current;
    if (el) { el.style.height = "auto"; el.style.height = Math.min(el.scrollHeight, 160) + "px"; }
  }, [text]);

  const dropPhoto = () => { if (photo) URL.revokeObjectURL(photo.url); setPhoto(null); };   // only for photos never sent

  function pickPhoto(file) {
    setMenuOpen(false);
    if (!file) return;
    if (!PHOTO_TYPES.includes(file.type)) { setPhotoError("Please choose a PNG, JPG or WEBP photo."); return; }
    if (file.size > MAX_PHOTO_MB * 1024 * 1024) { setPhotoError(`The photo must be ${MAX_PHOTO_MB} MB or smaller.`); return; }
    setPhotoError("");
    if (photo) URL.revokeObjectURL(photo.url);
    setPhoto({ file, url: URL.createObjectURL(file) });
    input.current && input.current.focus();
  }

  async function sendPhoto() {
    if (busy || !photo) return;
    const { file, url } = photo;
    const description = text.trim();
    // the thumbnail stays in the conversation, so its address is not revoked here
    add({ role: "user", kind: "text", text: description || "(photo only)", image: url, time: timeNow() });
    setPhoto(null); setText(""); setBusy(true);
    const typing = add({ role: "ai", kind: "typing" });
    try {
      const f = new FormData();
      f.append("image", file);
      if (description) f.append("description", description);
      if (sessionId.current) f.append("session_id", sessionId.current);
      const data = await api("/api/reports/photo/analyze", { method: "POST", form: f });
      remove(typing);
      if (data.session_id) { sessionId.current = data.session_id; onSaved(); }
      const say = (t) => add({ role: "ai", kind: "text", text: t, time: timeNow() });
      say(data.message);
      add({
        role: "ai", kind: "photo", result: data, preview: url, onMessage: say,
        onSent: (result) => add({ role: "ai", kind: "success", result }),
        onDiscarded: () => say("No problem, I removed the photo. Nothing was sent."),
      });
    } catch (e) {
      remove(typing);
      if (e.status !== 401) {
        add({ role: "ai", kind: "text", error: true, time: timeNow(),
              text: "I couldn't check that photo. " + e.message });
      }
    } finally {
      setBusy(false);
    }
  }

  const add = (item) => { const id = nextId.current++; setItems((l) => [...l, { id, ...item }]); return id; };
  const remove = (id) => setItems((l) => l.filter((x) => x.id !== id));

  async function send(preset) {
    if (photo && !preset) return sendPhoto();
    const question = (preset || text).trim();
    if (!question || busy) return;
    add({ role: "user", kind: "text", text: question, time: timeNow() });
    setText("");
    setBusy(true);
    const typing = add({ role: "ai", kind: "typing" });
    try {
      const data = await api("/api/ask", { method: "POST", json: { question, session_id: sessionId.current } });
      remove(typing);
      if (data.session_id) { sessionId.current = data.session_id; onSaved(); }
      add({ role: "ai", kind: "text", text: data.answer, suggestions: data.suggestions, time: timeNow() });
      if (data.type === "map" && data.map) {
        add({ role: "ai", kind: "map", map: data.map });
      }
      if (FORM_TYPES[data.type]) {
        add({
          role: "ai", kind: "form", formKind: FORM_TYPES[data.type], prefill: data.prefill,
          onSuccess: (result) => add({ role: "ai", kind: "success", result }),
        });
      }
    } catch (e) {
      remove(typing);
      if (e.status !== 401) {
        add({ role: "ai", kind: "text", error: true, time: timeNow(),
              text: "Could not get an answer. " + e.message + " Please try again." });
      }
    } finally {
      setBusy(false);
      input.current && input.current.focus();
    }
  }

  const canPhoto = user.role !== "admin";
  const extra = user.role === "admin"
    ? ["Show pending reports", "Show pending concerns"] : ["Show my pending concerns"];
  const CARDS = [
    ...(user.role === "instructor" ? [["Reserve a facility", RESERVE_QUICK]] : []),
    ["Report a concern", "How do I report a broken facility?"],
    ["Find a campus location", "Where is the NEMSU Tandag campus?"],
    ["Borrow equipment", "What equipment can I borrow?"],
  ];

  return (
    <div className="page chat-page">
      <main className="chat">
        <div className="messages" aria-live="polite">
          <div className="thread">
            {loadingChat && <ChatSkeleton />}
            {!loadingChat && items.length === 0 && (
              <div className="welcome">
                <img src="/logo.png" alt="" />
                <h2>How can I help you today?</h2>
                <p className="sub">Your NEMSU Tandag Main Campus Assistant</p>
                <div className="cards">
                  {CARDS.map(([title, q]) => (
                    <button key={title} type="button" className="card-btn" onClick={() => send(q)}>
                      <strong>{title}</strong><span>{q}</span>
                    </button>
                  ))}
                </div>
                {canPhoto && <p className="side-note">Something broken or unsafe? Tap the camera button to take or upload a photo, and say what's wrong by typing or speaking.</p>}
                {user.role === "instructor" && <p className="side-note">Instructors who cannot come to school can type "I am sick and cannot come to school" to file an availability report.</p>}
                {user.role === "student" && <p className="side-note">You can ask "Is Sir JP available today?" to check whether an instructor is in school.</p>}
              </div>
            )}
            {items.map((item) => <Row key={item.id} item={item} onSuggest={(q) => send(q)} />)}
            <div ref={bottom} />
          </div>
        </div>
        <div className="composer">
          <div className="composer-inner">
            <div className="chips-row" aria-label="Suggested questions">
              {[...QUICK, ...extra].map((q) => (
                <button key={q} className="chip" type="button" onClick={() => send(q)}>{q}</button>
              ))}
            </div>
            {photo && (
              <div className="attach-preview">
                <img src={photo.url} alt="Photo ready to send" />
                <span>Photo ready. Add a description (optional), then press send.</span>
                <button type="button" className="chip" onClick={dropPhoto} aria-label="Remove photo">Remove</button>
              </div>
            )}
            {photoError && <p className="form-error" role="alert">{photoError}</p>}
            <div className="input-area">
              {canPhoto && (
                <div className="attach-wrap">
                  <button type="button" className="attach-btn" aria-label="Add a photo" aria-expanded={menuOpen}
                          title="Report a problem with a photo" disabled={busy} onClick={() => setMenuOpen((o) => !o)}>
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" />
                    </svg>
                  </button>
                  {menuOpen && (
                    <div className="attach-menu" role="menu">
                      <button type="button" role="menuitem" onClick={() => cameraInput.current.click()}>Take a photo</button>
                      <button type="button" role="menuitem" onClick={() => galleryInput.current.click()}>Upload a photo</button>
                    </div>
                  )}
                  <input ref={cameraInput} type="file" accept="image/*" capture="environment" hidden
                         onChange={(e) => { pickPhoto(e.target.files[0]); e.target.value = ""; }} />
                  <input ref={galleryInput} type="file" accept="image/png,image/jpeg,image/webp" hidden
                         onChange={(e) => { pickPhoto(e.target.files[0]); e.target.value = ""; }} />
                </div>
              )}
              <textarea id="question" ref={input} rows={1} placeholder={photo ? "Describe the problem (optional)" : "Message NEMSAI"} aria-label="Your question"
                        value={text} onChange={(e) => setText(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
              <MicButton compact value={text} onChange={setText} disabled={busy} />
              <button className="send" type="button" disabled={busy || (!text.trim() && !photo)} onClick={() => send()} aria-label="Send">
                {busy ? "…" : <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5M5 12l7-7 7 7" /></svg>}
              </button>
            </div>
            <p className="footnote">Enter to send, Shift+Enter for a new line.{canPhoto && " Use the camera button to report a problem with a photo."}</p>
          </div>
        </div>
      </main>
    </div>
  );
}
