# ID / COR scanner (drop-in)

Copy the three files into `frontend/src/components/`:

- `IdScanner.jsx`        one scan slot (ID front, ID back, or COR)
- `DocumentScanners.jsx` the three slots together + `appendScans()` / `canSubmit()` helpers
- `scanner.css`          styles (imported by IdScanner, nothing to add to app.css)

## Use it in the student registration page (`/register`)

```jsx
import DocumentScanners, { appendScans, canSubmit } from "../components/DocumentScanners.jsx";

const [docs, setDocs] = useState({ idFront: null, idBack: null, cor: null });

// where the old file inputs were:
<DocumentScanners value={docs} onChange={setDocs} disabled={busy} />

// on submit (field names match POST /api/auth/student-registration):
const fd = new FormData();
fd.append("full_name", fullName);
fd.append("student_id", studentId);
fd.append("ai_review_consent", consent ? "true" : "");
appendScans(fd, docs);
// disable the Submit button until canSubmit(docs) is true (server needs the ID front OR the COR)
```

Camera access in browsers only works on HTTPS (or localhost). On plain http, or if permission is blocked,
the same buttons open the phone's camera app / gallery instead, so registration never gets stuck.

## Remove the microphone buttons

- `components/RecordForm.jsx`: delete `import MicButton from "./Voice.jsx";` and the `<MicButton ... />` line next to the textarea.
- `pages/Chat.jsx`: delete `import MicButton from "../components/Voice.jsx";` and `<MicButton compact value={text} onChange={setText} disabled={busy} />`.
