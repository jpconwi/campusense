import { useSearchParams } from "react-router-dom";
import AdminDataset from "./AdminDataset.jsx";

const TABS = [
  ["rooms", "Rooms"],
  ["campus", "Campus Information"],
  ["announcements", "Announcements"],
];

export default function AdminCampusData() {
  const [params, setParams] = useSearchParams();
  const view = TABS.some(([key]) => key === params.get("view")) ? params.get("view") : "rooms";

  function selectTab(nextView) {
    setParams({ view: nextView });
  }

  return <AdminDataset kind={view} tabs={TABS} onSelectTab={selectTab} />;
}
