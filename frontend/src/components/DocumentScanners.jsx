/* DocumentScanners.jsx - the three scan slots used when creating a student account.
 *
 *   const [docs, setDocs] = useState({ idFront: null, idBack: null, cor: null });
 *   <DocumentScanners value={docs} onChange={setDocs} />
 *   ...
 *   const fd = new FormData();                    // plus full_name, student_id, ai_review_consent
 *   appendScans(fd, docs);                         // sends the field names /api/auth/student-registration expects
 *
 * The server needs the ID front OR the COR (the ID back alone is not enough), so canSubmit() checks that.
 */
import IdScanner from "./IdScanner.jsx";

export function canSubmit(docs) { return !!(docs && (docs.idFront || docs.cor)); }

export function appendScans(formData, docs) {
  if (docs.idFront) formData.append("school_id_document", docs.idFront, docs.idFront.name);
  if (docs.idBack) formData.append("school_id_back_document", docs.idBack, docs.idBack.name);
  if (docs.cor) formData.append("cor_document", docs.cor, docs.cor.name);
  return formData;
}

export default function DocumentScanners({ value, onChange, disabled }) {
  const v = value || { idFront: null, idBack: null, cor: null };
  const set = (key) => (file) => onChange({ ...v, [key]: file });
  return (
    <div>
      <p className="ids-note ids">Scan your school ID, your COR, or both. The back of the ID is optional but helps the review.</p>
      <div className="ids-grid ids">
        <IdScanner kind="id-front" file={v.idFront} onChange={set("idFront")} required={!v.cor} disabled={disabled} />
        <IdScanner kind="id-back" file={v.idBack} onChange={set("idBack")} disabled={disabled} />
        <IdScanner kind="cor" file={v.cor} onChange={set("cor")} required={!v.idFront} disabled={disabled} />
      </div>
    </div>
  );
}
