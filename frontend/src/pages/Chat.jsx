/* Chat.jsx - the CampusSense AI chat window. */
import { Fragment, useEffect, useRef, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import RecordForm, { SuccessCard } from "../components/RecordForm.jsx";

const FORM_TYPES = {
  concern_form: "concern", report_form: "report", feedback_form: "feedback",
  reservation_form: "reservation", faculty_form: "faculty",
};

const timeNow = () => new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

// ---------- Markdown (safe: React escapes every piece of text) ----------
function Inline({ text }) {
  return text.split(/(\*\*.+?\*\*)/g).map((part, i) =>
    /^\*\*.+\*\*$/.test(part) ? <strong key={i}>{part.slice(2, -2)}</strong> : <Fragment key={i}>{part}</Fragment>);
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
function Row({ item }) {
  const ai = item.role === "ai";
  return (
    <div className={"message " + item.role}>
      {ai && <img className="avatar" src="/logo.png" alt="" />}
      <div className="stack">
        {item.kind === "typing" && (
          <div className="bubble rich"><span className="typing" aria-label="CampusSense AI is typing"><span></span><span></span><span></span></span></div>
        )}
        {item.kind === "text" && (
          <div className={"bubble" + (item.error ? " error" : "") + (ai && !item.error ? " rich" : "")}>
            {ai && !item.error ? <Markdown text={item.text} /> : item.text}
          </div>
        )}
        {item.kind === "form" && (
          <div className="bubble rich">
            <RecordForm kind={item.formKind} prefill={item.prefill} onSuccess={item.onSuccess} />
          </div>
        )}
        {item.kind === "map" && <MapCard map={item.map} />}
        {item.kind === "success" && <SuccessCard result={item.result} />}
        {(item.kind === "text") && <div className="time">{item.time}</div>}
      </div>
    </div>
  );
}

const QUICK = [
  "How do I reserve a room or facility?", "What equipment can I borrow?",
  "How do I report a broken facility?", "Where is the NEMSU Tandag campus?", "Where is the library?",
  "Which canteen is near the CBM area?",
];

export default function Chat() {
  const { user } = useAuth();
  const { chatKey } = useOutletContext();
  const [items, setItems] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const bottom = useRef(null);
  const input = useRef(null);
  const nextId = useRef(1);

  useEffect(() => { document.title = "Campus AI | NEMSU"; }, []);
  useEffect(() => { setItems([]); setText(""); input.current && input.current.focus(); }, [chatKey]);   // "New chat"
  useEffect(() => { bottom.current && bottom.current.scrollIntoView({ block: "end" }); }, [items]);
  useEffect(() => {                                    // grow the box while typing
    const el = input.current;
    if (el) { el.style.height = "auto"; el.style.height = Math.min(el.scrollHeight, 160) + "px"; }
  }, [text]);

  const add = (item) => { const id = nextId.current++; setItems((l) => [...l, { id, ...item }]); return id; };
  const remove = (id) => setItems((l) => l.filter((x) => x.id !== id));

  async function send(preset) {
    const question = (preset || text).trim();
    if (!question || busy) return;
    add({ role: "user", kind: "text", text: question, time: timeNow() });
    setText("");
    setBusy(true);
    const typing = add({ role: "ai", kind: "typing" });
    try {
      const data = await api("/api/ask", { method: "POST", json: { question } });
      remove(typing);
      add({ role: "ai", kind: "text", text: data.answer, time: timeNow() });
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

  return (
    <div className="page chat-page">
      <div className="layout">
        <aside aria-label="Suggested questions">
          <h2>Quick questions</h2>
          <div className="topic-list">
            {QUICK.map((q) => <button key={q} className="chip" type="button" onClick={() => send(q)}>{q}</button>)}
            {user.role === "admin" ? (
              <>
                <button className="chip" type="button" onClick={() => send("Show pending reports")}>Show pending reports</button>
                <button className="chip" type="button" onClick={() => send("Show pending concerns")}>Show pending concerns</button>
              </>
            ) : <button className="chip" type="button" onClick={() => send("Show my pending concerns")}>Show my pending concerns</button>}
          </div>
          {user.role === "instructor" && <p className="side-note">Instructors who cannot come to school can type "I am sick and cannot come to school" to file an availability report.</p>}
          {user.role === "student" && <p className="side-note">You can ask "Is Sir JP available today?" to check whether an instructor is in school.</p>}
        </aside>

        <main className="chat">
          <div className="messages" aria-live="polite">
            <div className="thread">
              {items.length === 0 && (
                <div className="welcome">
                  <img src="/logo.png" alt="" />
                  <h2>What do you need help with on campus?</h2>
                  <p>Ask about facilities, equipment, reservations, or maintenance concerns. Pick a quick question on the left or type your own below.</p>
                </div>
              )}
              {items.map((item) => <Row key={item.id} item={item} />)}
              <div ref={bottom} />
            </div>
          </div>
          <div className="composer">
            <div className="composer-inner">
              <div className="input-area">
                <textarea id="question" ref={input} rows={1} placeholder="Type your question" aria-label="Your question"
                          value={text} onChange={(e) => setText(e.target.value)}
                          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
                <button className="send" type="button" disabled={busy} onClick={() => send()}>{busy ? "Thinking..." : "Send"}</button>
              </div>
              <p className="footnote">Enter to send, Shift+Enter for a new line. North Eastern Mindanao State University, Surigao del Sur</p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
