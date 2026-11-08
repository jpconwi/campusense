import { Fragment, useCallback, useEffect, useState } from "react";
import { api, apiUrl, slug } from "../api.js";
import { useAuth } from "../auth.jsx";
import { EmptyState, Icon, Loading, PATHS, SearchBox, matches } from "../components/Ui.jsx";

/** "2026-10-29 11:26:02" -> date on one line, time below it. */
function DateCell({ value }) {
  const [date, ...time] = String(value || "").split(" ");
  return <span>{date}{time.length > 0 && <><br /><small className="muted">{time.join(" ")}</small></>}</span>;
}

function approvalClass(status) {
  if (status === "Approved") return "s-available";
  if (status === "Rejected") return "s-rejected";
  return "s-pending";
}

function reviewClass(status) {
  if (status === "Checked") return "s-reviewed";
  if (status === "Flagged") return "s-rejected";
  return "s-pending";
}

/** Preview a stored document; PDFs fall back to a link when the image can't render. */
function DocPreview({ title, url }) {
  const [failed, setFailed] = useState(false);
  if (!url) return null;
  return (
    <figure className="account-doc">
      <figcaption>{title}</figcaption>
      {failed
        ? <a href={url} target="_blank" rel="noreferrer">Open {title}</a>
        : <a href={url} target="_blank" rel="noreferrer" title={`Open ${title}`}>
            <img src={url} alt={title} loading="lazy" onError={() => setFailed(true)} />
          </a>}
    </figure>
  );
}

/** First-level check actions: approve/reject a pending account, or check/flag it. */
function CheckForm({ row, onChanged, scope }) {
  const { setFlash } = useAuth();
  const [note, setNote] = useState(row.review_note || "");
  const [busy, setBusy] = useState("");

  async function run(path, body, key) {
    setBusy(key);
    try {
      const result = await api(`/api/admin/accounts/${row.id}/${path}`, { method: "POST", json: body });
      setFlash({ text: result.message, kind: "info" });
      onChanged();
    } catch (err) {
      setFlash({ text: err.message, kind: "error" });
    } finally {
      setBusy("");
    }
  }

  async function deleteFlaggedAccount() {
    if (!window.confirm(`Delete ${row.name}'s account after the admin reported it suspicious?`)) return;
    setBusy("delete");
    try {
      const result = await api(`/api/admin/accounts/${row.id}/delete`, { method: "POST", json: {} });
      setFlash({ text: result.message, kind: "info" });
      onChanged();
    } catch (err) {
      setFlash({ text: err.message, kind: "error" });
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="account-check-actions">
      {scope !== "super_admin" && row.approval_status === "Pending" && (
        <div className="account-decide">
          <button className="btn small" type="button" disabled={busy !== ""}
            onClick={() => run("approve", {}, "approve")}>
            {busy === "approve" ? "Approving..." : "Approve account"}
          </button>
          <button className="btn small danger" type="button" disabled={busy !== ""}
            onClick={() => run("reject", {}, "reject")}>
            {busy === "reject" ? "Rejecting..." : "Reject account"}
          </button>
        </div>
      )}
      <label htmlFor={`check-note-${row.id}`}>Check note (optional)</label>
      <textarea id={`check-note-${row.id}`} rows={2} maxLength={500} value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder={scope === "super_admin"
          ? "Anything the account-check team should know about this account."
          : "Anything the super admin should know about this account."} />
      <div className="account-check-buttons">
        {scope === "super_admin" ? (
          <>
            <button className="btn small" type="button" disabled={busy !== ""}
              onClick={() => run("check", { note, flag: false }, "check")}>
              {busy === "check" ? "Saving..." : "Mark checked"}
            </button>
            <button className="btn small danger" type="button" disabled={busy !== ""}
              onClick={deleteFlaggedAccount}>
              {busy === "delete" ? "Deleting..." : "Delete account"}
            </button>
          </>
        ) : (
          <>
            <button className="btn small" type="button" disabled={busy !== ""}
              onClick={() => run("check", { note, flag: false }, "check")}>
              {busy === "check" ? "Saving..." : "Mark checked"}
            </button>
            <button className="btn small danger" type="button" disabled={busy !== ""}
              onClick={() => run("check", { note, flag: true }, "flag")}>
              {busy === "flag" ? "Saving..." : "Report to super admin"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function AccountDetail({ row, onChanged, scope }) {
  const base = `/api/admin/users/${row.id}`;
  return (
    <div className="account-detail">
      <div className="account-detail-head">
        <div>
          <h4>{row.name}</h4>
          <a href={`mailto:${row.email}`}>{row.email}</a>
        </div>
        <div className="account-detail-badges">
          <span className={"badge " + approvalClass(row.approval_status)}>{row.approval_status}</span>
          <span className={"badge " + reviewClass(row.review_status)}>{row.review_status || "Unreviewed"}</span>
        </div>
      </div>

      <div className="account-detail-layout">
        <div className="account-detail-main">
          <section className="account-detail-section">
            <h4>Account information</h4>
            <div className="account-detail-meta">
              <span><b>Source</b>{row.is_nemsu ? "NEMSU account" : "Personal Gmail"}</span>
              <span><b>Role</b>{row.registration_type || row.role || "-"}</span>
              <span><b>School ID</b>{row.student_id || "-"}</span>
              <span><b>Department</b>{row.department || "-"}</span>
              <span><b>Submitted</b>{row.created_at}</span>
              <span><b>Face review</b>{row.face_review_status === "AI Pose Passed" ? "Selfie framing passed" : row.face_review_status || "Not required"}</span>
            </div>
          </section>

          {row.verification_ai_note && (
            <section className="account-detail-section account-ai-note">
              <h4>Document screening</h4>
              <p>{row.verification_ai_note}</p>
            </section>
          )}

          {row.reviewed_by && (
            <section className="account-detail-section account-review-history">
              <h4>Previous check</h4>
              <p><b>{row.reviewed_by}</b> marked this account <b>{(row.review_status || "").toLowerCase()}</b>{row.reviewed_at ? ` on ${row.reviewed_at}` : ""}.</p>
              {row.review_note && <p className="muted">{row.review_note}</p>}
            </section>
          )}

          <section className="account-detail-section account-action-section">
            <h4>Review decision</h4>
            <CheckForm row={row} onChanged={onChanged} scope={scope} />
          </section>
        </div>

        <section className="account-detail-section account-docs">
          <h4>Documents and selfie</h4>
          <div className="account-doc-grid">
            {row.has_verification_document &&
              <DocPreview title={row.verification_document_kind === "cor" ? "COR" : "School ID front"}
                          url={apiUrl(`${base}/verification-document`)} />}
            {row.has_id_back_document && <DocPreview title="School ID back" url={apiUrl(`${base}/verification-document/id-back`)} />}
            {row.has_cor_document && <DocPreview title="Certificate of Registration" url={apiUrl(`${base}/verification-document/cor`)} />}
            {row.has_face_image && <DocPreview title="Face scan selfie" url={apiUrl(`${base}/face-image`)} />}
          </div>
          {row.has_face_scan_pdf && (
            <a className="account-pdf-link" href={apiUrl(`${base}/face-scan-pdf`)} target="_blank" rel="noreferrer">
              Open the selfie PDF
            </a>
          )}
          {!row.has_verification_document && !row.has_cor_document && !row.has_id_back_document && !row.has_face_image &&
            <p className="muted">No documents were uploaded for this account.</p>}
        </section>
      </div>
    </div>
  );
}

const FILTERS = [
  { key: "all", label: "All" },
  { key: "pending", label: "Pending approval" },
  { key: "unreviewed", label: "Needs check" },
  { key: "flagged", label: "Flagged" },
  { key: "checked", label: "Checked" },
];

export default function AdminAccounts({ scope = "admin", embedded = false }) {
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [openId, setOpenId] = useState(null);

  const load = useCallback(() => {
    setLoadError("");
    api("/api/admin/accounts").then(setData).catch((error) => {
      setLoadError(error.message || "Could not load account checks.");
    });
  }, []);
  useEffect(() => { document.title = "Account Checks | NEMSU"; load(); }, [load]);

  useEffect(() => {
    if (openId === null) return undefined;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event) => { if (event.key === "Escape") setOpenId(null); };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [openId]);

  if (loadError) return <div className="error" role="alert">{loadError}</div>;
  if (!data) return <Loading wide={1300} />;
  const rows = Array.isArray(data?.rows) ? data.rows : [];
  const counts = data?.counts || {};
  const scopedRows = scope === "super_admin"
    ? rows.filter((r) => r.review_status === "Flagged")
    : rows;
  const filtered = scopedRows.filter((r) => matches(r, q)).filter((r) => {
    if (filter === "pending") return r.approval_status === "Pending";
    if (filter === "unreviewed") return (r.review_status || "Unreviewed") === "Unreviewed";
    if (filter === "flagged") return r.review_status === "Flagged";
    if (filter === "checked") return r.review_status === "Checked";
    return true;
  });
  const opened = rows.find((r) => r.id === openId);

  return (
    <div className={embedded ? "account-checks-page embedded-account-checks" : "page account-checks-page"} style={{ maxWidth: 1300 }}>
      {!embedded && <h2 className="page-title">{scope === "super_admin" ? "Account Oversight" : "Account Checks"}</h2>}
      {!embedded && <p className="page-intro">{scope === "super_admin"
        ? "Review account checks, flagged registrations, and final approval status across the campus."
        : "Review NEMSU and personal-Gmail student and instructor registrations, then pass them on to the super admin."}</p>}

      {scope === "super_admin" && (
        <div className="account-summary" aria-label="Flagged account review totals">
          <div className="account-chip is-flagged"><b>{scopedRows.length}</b><span>Reported accounts</span></div>
        </div>
      )}
      {scope !== "super_admin" && <div className="account-summary" aria-label="Account review totals">
        <div className="account-chip is-pending"><b>{counts.pending}</b><span>Pending approval</span></div>
        <div className="account-chip is-unreviewed"><b>{counts.unreviewed}</b><span>Needs a check</span></div>
        <div className="account-chip is-flagged"><b>{counts.flagged}</b><span>Flagged</span></div>
      </div>}

      {scope !== "super_admin" && <div className="filters account-filters" aria-label="Filter accounts">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" aria-pressed={filter === f.key} className={filter === f.key ? "on" : ""}
            onClick={() => setFilter(f.key)}>{f.label}</button>
        ))}
      </div>}

      {scopedRows.length > 0 && (
        <SearchBox value={q} onChange={setQ} shown={filtered.length} total={rows.length}
          placeholder="Search accounts..." />
      )}

      {filtered.length ? (
        <div className="report-table-wrap">
          <table className="report-table">
            <thead>
              <tr>
                <th scope="col">Applicant</th>
                <th scope="col">Source</th>
                <th scope="col">Role</th>
                <th scope="col">Submitted</th>
                <th scope="col">Status</th>
                <th scope="col">Checked by</th>
                <th scope="col" aria-label="Details" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <Fragment key={r.id}>
                  <tr className={`report-row${openId === r.id ? " is-open" : ""}`} onClick={() => setOpenId(r.id)}>
                    <td className="report-who"><span>{r.name}</span><small className="muted">{r.email}</small></td>
                    <td>{r.is_nemsu ? "NEMSU" : "Personal Gmail"}</td>
                    <td>{r.registration_type || r.role || "-"}</td>
                    <td className="report-when"><DateCell value={r.created_at} /></td>
                    <td>
                      <span className={"badge " + approvalClass(r.approval_status)}>{r.approval_status}</span>{" "}
                      <span className={"badge " + reviewClass(r.review_status)}>{r.review_status || "Unreviewed"}</span>
                    </td>
                    <td className="report-assignee">{r.reviewed_by || <span className="muted">Unreviewed</span>}</td>
                    <td className="report-toggle-cell">
                      <button type="button" className="report-toggle" aria-label={`Show details for ${r.name}`}
                        onClick={(event) => { event.stopPropagation(); setOpenId(r.id); }}>
                        <Icon d={PATHS.arrow} size={16} />
                      </button>
                    </td>
                  </tr>
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title={scope === "super_admin" ? "No reported accounts" : (rows.length ? "No matches" : "No accounts to check")}>
          {scopedRows.length ? "Nothing matches this search and filter."
            : scope === "super_admin"
              ? "Accounts reported as suspicious by admins will appear here."
              : "New NEMSU or personal-Gmail registrations will appear here for checking."}
        </EmptyState>
      )}

      {opened && (
        <div className="report-dialog-backdrop" onClick={() => setOpenId(null)}>
          <section className="report-dialog account-dialog" role="dialog" aria-modal="true" aria-labelledby="account-dialog-title"
            onClick={(event) => event.stopPropagation()}>
            <header className="report-dialog-header">
              <div>
                <span className="report-dialog-eyebrow">Account check</span>
                <h3 id="account-dialog-title">{opened.name}</h3>
              </div>
              <button type="button" className="report-dialog-close" onClick={() => setOpenId(null)}
                aria-label="Close account details" autoFocus>×</button>
            </header>
            <div className="report-dialog-content">
              <AccountDetail key={opened.id} row={opened} onChanged={load} scope={scope} />
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
