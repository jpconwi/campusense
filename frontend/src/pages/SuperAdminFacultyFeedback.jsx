import { useSearchParams } from "react-router-dom";
import AdminFaculty from "./AdminFaculty.jsx";
import AdminList from "./AdminList.jsx";

const VIEWS = [
  ["faculty", "Faculty Reports", "/admin/faculty-feedback?view=faculty"],
  ["all", "All Feedback", "/admin/faculty-feedback?view=all&scope=all"],
  ["system-technical", "System & Technical", "/admin/faculty-feedback?view=system-technical&scope=system-technical"],
];

export default function SuperAdminFacultyFeedback() {
  const [params, setParams] = useSearchParams();
  const view = VIEWS.some(([key]) => key === params.get("view")) ? params.get("view") : "faculty";

  function selectView(nextView) {
    const selected = VIEWS.find(([key]) => key === nextView);
    setParams(new URLSearchParams(selected[2].split("?")[1]));
  }

  return (
    <>
      <div className="page" style={{ maxWidth: 1300, paddingBottom: 0 }}>
        <h2 className="page-title">Faculty &amp; Feedback</h2>
        <div className="filters" role="tablist" aria-label="Faculty and feedback sections">
          {VIEWS.map(([key, label]) => (
            <button key={key} type="button" role="tab" aria-selected={view === key}
              className={view === key ? "on" : ""} onClick={() => selectView(key)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      {view === "faculty" ? <AdminFaculty /> : <AdminList kind="feedback" />}
    </>
  );
}
