import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, apiUrl } from "../api.js";
import { useAuth } from "../auth.jsx";
import { EmptyState, Icon, Loading, PATHS } from "../components/Ui.jsx";

const STATUSES = ["Pending", "Checked", "Flagged", "Rejected", "All"];
function parseDate(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2}) (\d{1,2}):(\d{2}):(\d{2}) (AM|PM)$/i);
  if (!match) return new Date(value);
  let hour = Number(match[4]) % 12;
  if (match[7].toUpperCase() === "PM") hour += 12;
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), hour,
    Number(match[5]), Number(match[6]));
}
const displayDate = (value) => value ? parseDate(value).toLocaleString() : "—";
function relativeDate(value) {
  if (!value) return "";
  const minutes = Math.max(0, Math.floor((Date.now() - parseDate(value).getTime()) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} ${minutes === 1 ? "minute" : "minutes"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ${hours === 1 ? "hour" : "hours"} ago`;
  const days = Math.floor(hours / 24);
  return `${days} ${days === 1 ? "day" : "days"} ago`;
}
const statusTone = (status) => status === "Approved" || status === "Checked" ? "s-available"
  : status === "Rejected" || status === "Flagged" ? "s-rejected" : "s-pending";

function FilePreview({ title, available, url, onOpen }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  return <figure className="account-file">
    <figcaption>{title}</figcaption>
    {available ? failed ? <a className="account-file-thumb account-file-fallback" href={url} target="_blank" rel="noreferrer">Preview unavailable · Open file</a>
      : <button className="account-file-thumb" type="button" onClick={() => onOpen({ title, url })} aria-label={`Open ${title}`}>
        {!loaded && <span className="account-file-skeleton" aria-label={`Loading ${title}`} />}
        <img src={url} alt={title} onLoad={() => setLoaded(true)} onError={() => setFailed(true)} />
      </button> : <div className="account-file-missing">Not uploaded</div>}
  </figure>;
}

function ConfirmDialog({ title, text, confirmLabel, tone, reason, setReason, onCancel, onConfirm, busy }) {
  function trapDialogTab(event) {
    if (event.key === "Escape") { event.stopPropagation(); onCancel(); return; }
    if (event.key !== "Tab") return;
    const items = [...event.currentTarget.querySelectorAll("button:not(:disabled), textarea:not(:disabled)")];
    if (!items.length) return;
    if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items.at(-1).focus(); }
    else if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0].focus(); }
  }
  return <div className="account-confirm-shade" onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel(); }}>
    <section className="account-confirm" role="alertdialog" aria-modal="true" aria-labelledby="account-confirm-title" onKeyDown={trapDialogTab}>
      <h4 id="account-confirm-title">{title}</h4>
      <p>{text}</p>
      {reason !== undefined && <label>Reason (optional)
        <textarea value={reason} maxLength={300} rows={4} onChange={(event) => setReason(event.target.value)} />
      </label>}
      <div className="account-confirm-actions">
        <button className="btn small ghost" type="button" onClick={onCancel} disabled={busy} autoFocus>Cancel</button>
        <button className={`btn small ${tone || ""}`} type="button" onClick={onConfirm} disabled={busy}>
          {busy ? <><span className="spinner" aria-hidden="true" /> Working…</> : confirmLabel}
        </button>
      </div>
    </section>
  </div>;
}

function DocumentLightbox({ file, onClose }) {
  const [zoom, setZoom] = useState(1);
  useEffect(() => {
    const key = (event) => { if (event.key === "Escape") { event.stopPropagation(); onClose(); } };
    document.addEventListener("keydown", key, true);
    return () => document.removeEventListener("keydown", key, true);
  }, [onClose]);
  return <div className="account-lightbox" role="dialog" aria-modal="true" aria-label={`${file.title} preview`} onClick={onClose}>
    <div className="account-lightbox-toolbar" onClick={(event) => event.stopPropagation()}>
      <strong>{file.title}</strong>
      <button type="button" aria-label="Zoom out" onClick={() => setZoom((value) => Math.max(.5, value - .25))}>−</button>
      <span>{Math.round(zoom * 100)}%</span>
      <button type="button" aria-label="Zoom in" onClick={() => setZoom((value) => Math.min(3, value + .25))}>+</button>
      <a href={file.url} target="_blank" rel="noreferrer">Open file</a>
      <button type="button" aria-label="Close preview" onClick={onClose}>×</button>
    </div>
    <div className="account-lightbox-stage" onClick={(event) => event.stopPropagation()}>
      <img src={file.url} alt={file.title} style={{ transform: `scale(${zoom})` }} />
    </div>
  </div>;
}

function AccountDetail({ row, isSuperAdmin, onChanged }) {
  const { setFlash } = useAuth();
  const [note, setNote] = useState(row.review_note || "");
  const [busy, setBusy] = useState("");
  const [confirm, setConfirm] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [lightbox, setLightbox] = useState(null);
  const missing = row.approval_missing || [];
  const canApprove = missing.length === 0;
  const canCheck = ["Pending", "Approved"].includes(row.approval_status);
  const docsPresent = row.registration_type === "instructor" || row.has_verification_document;

  async function run(action, body = {}, busyKey = action) {
    setBusy(busyKey);
    try {
      const result = await api(`/api/admin/accounts/${row.id}/${action}`, { method: "POST", json: body });
      setFlash({ text: result.message, kind: "info" });
      setConfirm("");
      await onChanged();
    } catch (error) {
      setFlash({ text: error.message, kind: "error" });
      if (error.missing?.length) setFlash({ text: `${error.message} ${error.missing.join(" · ")}`, kind: "error" });
    } finally { setBusy(""); }
  }

  function startFlag() {
    if (!note.trim()) {
      document.getElementById(`account-note-${row.id}`)?.focus();
      setFlash({ text: "Add a note explaining why this account is suspicious before flagging it.", kind: "error" });
      return;
    }
    run("check", { note, flag: true }, "flag");
  }

  const base = `/api/admin/users/${row.id}`;
  return <>
    <div className="account-detail">
      <div className="account-detail-identity">
        <div className="account-badges"><span className="badge role-badge">{row.role || row.registration_type || "Applicant"}</span>
          <span className={`badge ${statusTone(row.approval_status)}`}>{row.approval_status}</span></div>
        <div className="account-submitted">Submitted {displayDate(row.created_at)}</div>
      </div>

      <section className="account-panel-section">
        <h4>Review checklist</h4>
        <ol className="account-checklist">
          <li className={docsPresent ? "is-done" : "is-blocked"}><span>{docsPresent ? "✓" : "1"}</span><div><b>Documents present</b><small>{row.registration_type === "instructor" ? "No ID document required for this registration type" : docsPresent ? "School ID document uploaded" : "Student ID document missing"}</small></div></li>
          <li className={row.face_review_status === "Verified" || row.face_review_status === "Not required" ? "is-done" : "is-blocked"}><span>{row.face_review_status === "Verified" || row.face_review_status === "Not required" ? "✓" : "2"}</span><div><b>Selfie verified</b><small>{row.face_review_status === "Not required" ? "Not required" : row.face_review_status === "Verified" ? "Verified by an administrator" : "Human review required · current: " + (row.face_review_status || "Pending")}</small></div></li>
          <li className={row.review_status === "Checked" || isSuperAdmin ? "is-done" : "is-blocked"}><span>{row.review_status === "Checked" || isSuperAdmin ? "✓" : "3"}</span><div><b>First-level check passed</b><small>{isSuperAdmin && row.review_status !== "Checked" ? "Super Admin may approve without this check" : row.review_status === "Checked" ? "Checked by an administrator" : row.review_status === "Flagged" ? "Account was flagged" : "First-level check not done"}</small></div></li>
          <li className={row.approval_status === "Approved" ? "is-done" : "is-blocked"}><span>{row.approval_status === "Approved" ? "✓" : "4"}</span><div><b>Account approved</b><small>{row.approval_status === "Approved" ? "Approved" : "Final approval is still pending"}</small></div></li>
        </ol>
        {row.approval_status === "Pending" && <div className={`account-blockers${canApprove ? " clear" : ""}`} aria-live="polite">
          <b>{canApprove ? "Ready for approval" : "Approval blocked"}</b>
          {canApprove ? <span>All approval requirements are met.</span> : <ul>{missing.map((item) => <li key={item}>{item}</li>)}</ul>}
        </div>}
      </section>

      <section className="account-panel-section">
        <h4>Application details</h4>
        <dl className="account-facts">
          <div><dt>Registration type</dt><dd>{row.registration_type || "—"}</dd></div>
          <div><dt>Student / instructor ID</dt><dd>{row.student_id || "—"}</dd></div>
          <div><dt>Department</dt><dd>{row.department || "—"}</dd></div>
          <div><dt>Account source</dt><dd>{row.is_nemsu ? "NEMSU" : "Personal Gmail"}</dd></div>
        </dl>
        {row.verification_ai_note && <p className="account-ai-note"><b>Document screening note</b>{row.verification_ai_note}</p>}
        {row.reviewed_by && <div className="account-review-note"><b>{row.review_status === "Checked" ? "Checked by" : "Reviewed by"} {row.reviewed_by}</b>{row.reviewed_at && <span> · {relativeDate(row.reviewed_at)}</span>}{row.review_note && <p>{row.review_note}</p>}</div>}
        {row.rejection_reason && <div className="account-rejection-note"><b>Rejection reason</b><p>{row.rejection_reason}</p></div>}
      </section>

      <section className="account-panel-section">
        <h4>Documents and selfie</h4>
        <div className="account-files-grid">
          <FilePreview title="ID front" available={row.has_verification_document && row.verification_document_kind !== "cor"} url={apiUrl(`${base}/verification-document`)} onOpen={setLightbox} />
          <FilePreview title="ID back" available={row.has_id_back_document} url={apiUrl(`${base}/verification-document/id-back`)} onOpen={setLightbox} />
          <FilePreview title="COR" available={row.has_cor_document || (row.has_verification_document && row.verification_document_kind === "cor")} url={apiUrl(`${base}${row.has_cor_document ? "/verification-document/cor" : "/verification-document"}`)} onOpen={setLightbox} />
          <FilePreview title="Selfie" available={row.has_face_image} url={apiUrl(`${base}/face-image`)} onOpen={setLightbox} />
        </div>
        {row.has_face_image && <div className="account-selfie-review">
          <div><b>Selfie review: {row.face_review_status || "Pending"}</b><span>AI pose detection does not verify identity.</span></div>
          <div className="account-selfie-actions">
            <button className="btn small success" type="button" disabled={Boolean(busy) || !canCheck} onClick={() => run("face-review", { status: "Verified" }, "face-verified")}>
              {busy === "face-verified" ? <><span className="spinner" aria-hidden="true" /> Saving…</> : "Mark Verified"}</button>
            <button className="btn small outline-danger" type="button" disabled={Boolean(busy) || !canCheck} onClick={() => run("face-review", { status: "Rejected" }, "face-rejected")}>
              {busy === "face-rejected" ? <><span className="spinner" aria-hidden="true" /> Saving…</> : "Mark Rejected"}</button>
          </div>
        </div>}
      </section>

      <section className="account-panel-section account-note-section">
        <label htmlFor={`account-note-${row.id}`}>Check note</label>
        <textarea id={`account-note-${row.id}`} value={note} maxLength={500} rows={3} onChange={(event) => setNote(event.target.value)} placeholder="Add a note for the next reviewer…" />
        <small>{note.length}/500 characters</small>
      </section>
    </div>

    <footer className="account-sticky-actions">
      <button className="btn small" type="button" disabled={Boolean(busy) || !canCheck} onClick={() => run("check", { note, flag: false })}>
        {busy === "check" ? <><span className="spinner" aria-hidden="true" /> Saving…</> : "Mark checked"}
      </button>
      <button className="btn small outline-amber" type="button" disabled={Boolean(busy) || !canCheck} onClick={startFlag}>
        {busy === "flag" ? <><span className="spinner" aria-hidden="true" /> Saving…</> : "Flag as suspicious"}
      </button>
      <button className="btn small outline-danger" type="button" disabled={Boolean(busy) || row.approval_status !== "Pending"} onClick={() => setConfirm("reject")}>Reject</button>
      <button className="btn small success" type="button" disabled={Boolean(busy) || !canApprove} aria-describedby={`approve-help-${row.id}`} onClick={() => setConfirm("approve")}>
        {busy === "approve" ? <><span className="spinner" aria-hidden="true" /> Approving…</> : "Approve"}
      </button>
      {isSuperAdmin && row.approval_status === "Rejected" && <button className="btn small outline-danger" type="button" disabled={Boolean(busy)} onClick={() => setConfirm("delete")}>Delete rejected account</button>}
      <span id={`approve-help-${row.id}`} className={`account-approve-help${canApprove ? " ready" : ""}`}>
        {row.approval_status !== "Pending" ? `This account is ${String(row.approval_status).toLowerCase()}.`
          : canApprove ? "Ready to approve." : `Cannot approve: ${missing.join(" · ")}`}
      </span>
    </footer>

    {confirm && <ConfirmDialog
      title={confirm === "approve" ? "Confirm account approval" : confirm === "delete" ? "Delete rejected account" : "Reject account registration"}
      text={confirm === "approve" ? `Approve ${row.name} (${row.email})? They will be able to sign in.` : confirm === "delete" ? `Delete ${row.name} (${row.email})? The account will be disabled and scheduled for permanent deletion.` : `Reject ${row.name}'s registration? Add a reason that will be saved with the account.`}
      confirmLabel={confirm === "approve" ? "Approve account" : confirm === "delete" ? "Delete account" : "Reject account"}
      tone={confirm === "approve" ? "success" : "outline-danger"}
      reason={confirm === "reject" ? rejectReason : undefined} setReason={setRejectReason}
      busy={Boolean(busy)} onCancel={() => setConfirm("")}
      onConfirm={() => run(confirm, confirm === "reject" ? { reason: rejectReason } : {})} />}
    {lightbox && <DocumentLightbox file={lightbox} onClose={() => setLightbox(null)} />}
  </>;
}

function AccountRow({ row, onOpen }) {
  const status = row.review_status || "Unreviewed";
  return <tr className="account-data-row" onClick={() => onOpen(row)}>
      <td><button className="account-row-open" type="button" onClick={(event) => { event.stopPropagation(); onOpen(row); }}>
        <b>{row.name}</b><span>{row.email}</span></button></td>
      <td>{row.role || "—"}</td><td>{row.registration_type || "—"}</td><td>{displayDate(row.created_at)}</td>
      <td><span className={`badge ${statusTone(row.approval_status)}`}>{row.approval_status}</span> <span className={`badge ${statusTone(status)}`}>{status}</span></td>
      <td>{row.reviewed_by || <span className="muted">Not checked</span>}</td>
    </tr>;
}

function AccountMobileCard({ row, onOpen }) {
  const status = row.review_status || "Unreviewed";
  return <button className="account-mobile-card" type="button" onClick={() => onOpen(row)}>
      <span className="account-mobile-head"><b>{row.name}</b><span className={`badge ${statusTone(row.approval_status)}`}>{row.approval_status}</span></span>
      <span>{row.email}</span><span className="account-mobile-meta">{row.role || row.registration_type} · Submitted {displayDate(row.created_at)}</span>
      <span className="account-mobile-meta">{status} · {row.reviewed_by ? `Checked by ${row.reviewed_by}` : "Not checked"}</span>
    </button>
}

export default function AdminAccounts({ embedded = false }) {
  const { user, setFlash } = useAuth();
  const isSuperAdmin = user?.role === "super_admin";
  const [params, setParams] = useSearchParams();
  const requestedStatus = params.get("status") || "Pending";
  const activeStatus = STATUSES.includes(requestedStatus) ? requestedStatus : "Pending";
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState(null);
  const dialogRef = useRef(null);

  const load = useCallback(async () => {
    setLoadError("");
    try { setData(await api("/api/admin/accounts")); }
    catch (error) { setLoadError(error.message || "Could not load accounts."); }
  }, []);
  useEffect(() => { document.title = `${embedded ? "Users · Account Checks" : "Account Checks"} | NEMSU`; load(); }, [load, embedded]);
  useEffect(() => {
    if (!params.has("status") || !STATUSES.includes(params.get("status"))) {
      setParams((previous) => {
        const next = embedded ? new URLSearchParams(previous) : new URLSearchParams();
        next.set("status", "Pending");
        return next;
      }, { replace: true });
    }
  }, [params, setParams, embedded]);
  useEffect(() => {
    if (openId === null) return undefined;
    const before = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const dialog = dialogRef.current;
    const focusable = () => [...(dialog?.querySelectorAll("button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex='0']") || [])];
    focusable()[0]?.focus();
    const keydown = (event) => {
      if (event.key === "Escape") { event.preventDefault(); setOpenId(null); return; }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items.at(-1).focus(); }
      else if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0].focus(); }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.body.style.overflow = before; document.removeEventListener("keydown", keydown); };
  }, [openId]);

  const rows = data?.rows || [];
  const counts = data?.counts || {};
  const filtered = useMemo(() => rows.filter((row) => {
    const matchStatus = activeStatus === "All" || (activeStatus === "Rejected"
      ? row.approval_status === "Rejected"
      : activeStatus === "Pending"
        ? row.approval_status === "Pending" || (row.approval_status !== "Rejected" && (row.review_status || "Unreviewed") === "Unreviewed" && row.is_nemsu)
        : row.review_status === activeStatus);
    const q = query.trim().toLowerCase();
    const matchQuery = !q || [row.name, row.email, row.student_id, row.id].some((item) => String(item || "").toLowerCase().includes(q));
    return matchStatus && matchQuery;
  }), [rows, activeStatus, query]);
  const opened = rows.find((row) => row.id === openId);

  function chooseStatus(status) {
    const next = embedded ? new URLSearchParams(params) : new URLSearchParams();
    next.set("status", status);
    setParams(next);
  }

  if (loadError) return <div className="page account-checks-page"><h2 className="page-title">Account Checks</h2>
    <div className="account-load-error" role="alert"><Icon d={PATHS.alert} /><div><b>Accounts could not be loaded</b><p>{loadError}</p>
      <button type="button" className="btn small" onClick={load}>Retry</button></div></div></div>;
  if (!data) return <main className="page account-checks-page"><h2 className="page-title">Account Checks</h2><Loading wide={1200} label="Loading account checks…" /></main>;

  return <main className="page account-checks-page">
    <h2 className="page-title">Account Checks</h2>
    <p className="page-intro">Review documents and identity checks, then approve eligible student and instructor accounts.</p>

    <div className="account-summary" aria-label="Account review counts">
      <button type="button" className={`account-chip is-pending${activeStatus === "Pending" ? " selected" : ""}`} onClick={() => chooseStatus("Pending")} aria-pressed={activeStatus === "Pending"}>
        <b>{counts.pending || 0}</b><span>Waiting for review</span></button>
      <button type="button" className={`account-chip is-checked${activeStatus === "Checked" ? " selected" : ""}`} onClick={() => chooseStatus("Checked")} aria-pressed={activeStatus === "Checked"}>
        <b>{counts.checked || 0}</b><span>Checked</span></button>
      <button type="button" className={`account-chip is-flagged${activeStatus === "Flagged" ? " selected" : ""}`} onClick={() => chooseStatus("Flagged")} aria-pressed={activeStatus === "Flagged"}>
        <b>{counts.flagged || 0}</b><span>Flagged</span></button>
      <button type="button" className={`account-chip is-rejected${activeStatus === "Rejected" ? " selected" : ""}`} onClick={() => chooseStatus("Rejected")} aria-pressed={activeStatus === "Rejected"}>
        <b>{counts.rejected || 0}</b><span>Rejected</span></button>
    </div>

    <div className="account-list-toolbar">
      <div className="account-tabs" role="tablist" aria-label="Account review status">
        {[["Pending", "Needs review"], ["Checked", "Checked"], ["Flagged", "Flagged"], ["Rejected", "Rejected"], ["All", "All"]].map(([key, label]) =>
          <button key={key} type="button" role="tab" aria-selected={activeStatus === key} className={activeStatus === key ? "active" : ""} onClick={() => chooseStatus(key)}>{label}</button>)}
      </div>
      <label className="account-search"><Icon d={PATHS.search} size={18} /><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name, email, student ID, or account ID" aria-label="Search name, email, student ID, or account ID" /></label>
    </div>

    {filtered.length ? <>
      <div className="account-desktop-table"><table>
        <thead><tr><th>Applicant</th><th>Role</th><th>Registration type</th><th>Submitted</th><th>Status</th><th>Reviewer</th></tr></thead>
        <tbody>{filtered.map((row) => <AccountRow key={row.id} row={row} onOpen={(item) => setOpenId(item.id)} />)}</tbody>
      </table></div>
      <div className="account-mobile-list">{filtered.map((row) => <AccountMobileCard key={row.id} row={row} onOpen={(item) => setOpenId(item.id)} />)}</div>
    </> : <EmptyState icon={PATHS.users} title={activeStatus === "Pending" && !query ? "No accounts waiting. You're all caught up." : "No matching accounts"}>
      {query ? "Try a different name, email, or student ID." : activeStatus === "All" ? "No registrations are available." : `There are no accounts in the ${activeStatus.toLowerCase()} view.`}
    </EmptyState>}

    {opened && <div className="account-drawer-shade" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpenId(null); }}>
      <section ref={dialogRef} className="account-drawer" role="dialog" aria-modal="true" aria-labelledby="account-drawer-title" tabIndex={-1}>
        <header className="account-drawer-header">
          <div><span>Account review</span><h3 id="account-drawer-title">{opened.name}</h3><a href={`mailto:${opened.email}`}>{opened.email}</a></div>
          <button className="account-drawer-close" type="button" onClick={() => setOpenId(null)} aria-label="Close account details">×</button>
        </header>
        <AccountDetail key={opened.id} row={opened} isSuperAdmin={isSuperAdmin} onChanged={load} />
      </section>
    </div>}
  </main>;
}
