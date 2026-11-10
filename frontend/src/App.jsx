import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Layout from "./components/Layout.jsx";
import { AppSkeleton } from "./components/Skeletons.jsx";
import AdminDashboard from "./pages/AdminDashboard.jsx";
import AdminAccounts from "./pages/AdminAccounts.jsx";
import AdminDataset from "./pages/AdminDataset.jsx";
import AdminFaculty from "./pages/AdminFaculty.jsx";
import AdminHelpMessages from "./pages/AdminHelpMessages.jsx";
import AdminList from "./pages/AdminList.jsx";
import AdminLogin from "./pages/AdminLogin.jsx";
import AdminUsers from "./pages/AdminUsers.jsx";
import SuperAdmin from "./pages/SuperAdmin.jsx";
import Chat from "./pages/Chat.jsx";
import Faculty from "./pages/Faculty.jsx";
import Home from "./pages/Home.jsx";
import Login from "./pages/Login.jsx";
import MyList from "./pages/MyList.jsx";
import NotFound from "./pages/NotFound.jsx";
import Notifications from "./pages/Notifications.jsx";
import NemsuRegister from "./pages/NemsuRegister.jsx";
import Profile from "./pages/Profile.jsx";
import Register from "./pages/Register.jsx";
import RoleSelect from "./pages/RoleSelect.jsx";

/** Signed in AND role chosen. `roles` limits who may open the page. */
function Guard({ roles, children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === null) return <Navigate to="/select-role" replace />;
  const allowed = roles?.includes("admin") && user.role === "super_admin";
  if (roles && !roles.includes(user.role) && !allowed) {
    // admin pages look like they do not exist; other pages go back home
    return roles.some((role) => ["admin", "super_admin"].includes(role)) ? <NotFound /> : <Navigate to="/" replace />;
  }
  return children;
}

function AccountChecksRoute() {
  const { user } = useAuth();
  if (user?.role === "super_admin") return <Navigate to="/admin/users?view=checks" replace />;
  return <Guard roles={["admin"]}><AdminAccounts /></Guard>;
}

export default function App() {
  const { loading } = useAuth();
  if (loading) return <AppSkeleton />;

  const page = (element, roles) => <Guard roles={roles}>{element}</Guard>;
  const person = ["student", "instructor"];

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/register/nemsu" element={<NemsuRegister />} />
      <Route path="/select-role" element={<RoleSelect />} />
      <Route path="/admin/login/:secret" element={<AdminLogin />} />

      <Route element={<Layout />}>
        <Route path="/" element={page(<Home />)} />
        <Route path="/notifications" element={page(<Notifications />, person)} />
        <Route path="/ai" element={page(<Chat />)} />
        <Route path="/profile" element={page(<Profile />)} />
        <Route path="/concerns" element={<Navigate to="/reports" replace />} />
        <Route path="/reports" element={page(<MyList kind="reports" />, person)} />
        <Route path="/feedback" element={page(<MyList kind="feedback" />, person)} />
        <Route path="/my-feedback" element={page(<MyList kind="feedback" hideForm />, person)} />
        <Route path="/reservations" element={page(<MyList kind="reservations" />, ["instructor"])} />
        <Route path="/faculty" element={page(<Faculty />, ["instructor"])} />

        <Route path="/admin" element={page(<AdminDashboard />, ["admin"])} />
        <Route path="/admin/accounts" element={<AccountChecksRoute />} />
        <Route path="/admin/users" element={page(<AdminUsers />, ["super_admin"])} />
        <Route path="/admin/system" element={page(<SuperAdmin />, ["super_admin"])} />
        <Route path="/admin/online-users" element={<Navigate to="/admin/users?view=online" replace />} />
        <Route path="/admin/help-messages" element={page(<AdminHelpMessages />, ["super_admin"])} />
        <Route path="/admin/concerns" element={<Navigate to="/admin/reports?type=concern" replace />} />
        <Route path="/admin/faculty" element={page(<AdminFaculty />, ["admin"])} />
        <Route path="/admin/rooms" element={page(<AdminDataset kind="rooms" />, ["super_admin"])} />
        <Route path="/admin/campus" element={page(<AdminDataset kind="campus" />, ["super_admin"])} />
        <Route path="/admin/announcements" element={page(<AdminDataset kind="announcements" />, ["admin"])} />
        {["reports", "feedback"].map((k) => (
          <Route key={k} path={`/admin/${k}`} element={page(<AdminList kind={k} />, ["admin"])} />
        ))}
        <Route path="/admin/reservations" element={page(<AdminList kind="reservations" />, ["admin"])} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
