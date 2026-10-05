import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Layout from "./components/Layout.jsx";
import AdminDashboard from "./pages/AdminDashboard.jsx";
import AdminDataset from "./pages/AdminDataset.jsx";
import AdminFaculty from "./pages/AdminFaculty.jsx";
import AdminList from "./pages/AdminList.jsx";
import AdminLogin from "./pages/AdminLogin.jsx";
import AdminUsers from "./pages/AdminUsers.jsx";
import Chat from "./pages/Chat.jsx";
import Faculty from "./pages/Faculty.jsx";
import Home from "./pages/Home.jsx";
import Login from "./pages/Login.jsx";
import MyList from "./pages/MyList.jsx";
import NotFound from "./pages/NotFound.jsx";
import Profile from "./pages/Profile.jsx";
import RoleSelect from "./pages/RoleSelect.jsx";

/** Signed in AND role chosen. `roles` limits who may open the page. */
function Guard({ roles, children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === null) return <Navigate to="/select-role" replace />;
  if (roles && !roles.includes(user.role)) {
    // admin pages look like they do not exist; other pages go back home
    return roles.includes("admin") ? <NotFound /> : <Navigate to="/" replace />;
  }
  return children;
}

export default function App() {
  const { loading } = useAuth();
  if (loading) return null;

  const page = (element, roles) => <Guard roles={roles}>{element}</Guard>;
  const person = ["student", "instructor"];

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/select-role" element={<RoleSelect />} />
      <Route path="/admin/login/:secret" element={<AdminLogin />} />

      <Route element={<Layout />}>
        <Route path="/" element={page(<Home />)} />
        <Route path="/ai" element={page(<Chat />)} />
        <Route path="/profile" element={page(<Profile />)} />
        <Route path="/concerns" element={page(<MyList kind="concerns" />, person)} />
        <Route path="/reports" element={page(<MyList kind="reports" />, person)} />
        <Route path="/feedback" element={page(<MyList kind="feedback" />, person)} />
        <Route path="/reservations" element={page(<MyList kind="reservations" />, person)} />
        <Route path="/faculty" element={page(<Faculty />, ["instructor"])} />

        <Route path="/admin" element={page(<AdminDashboard />, ["admin"])} />
        <Route path="/admin/users" element={page(<AdminUsers />, ["admin"])} />
        <Route path="/admin/faculty" element={page(<AdminFaculty />, ["admin"])} />
        <Route path="/admin/rooms" element={page(<AdminDataset kind="rooms" />, ["admin"])} />
        <Route path="/admin/campus" element={page(<AdminDataset kind="campus" />, ["admin"])} />
        {["concerns", "reports", "feedback", "reservations"].map((k) => (
          <Route key={k} path={`/admin/${k}`} element={page(<AdminList kind={k} />, ["admin"])} />
        ))}
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
