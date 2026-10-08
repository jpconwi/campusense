import { useEffect } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { Header } from "../components/Layout.jsx";
import { useAuth } from "../auth.jsx";

const API_BASE = import.meta.env.VITE_API_URL || "";

// The server sends a short code in ?error=... and this page turns it into a message.
const MESSAGES = {
  wrong_account: "Please use your official NEMSU Google account.",
  cancelled: "Google sign-in was cancelled or failed. Please try again.",
  not_configured:
    "Google sign-in is not configured yet. Please contact the administrator.",
  deactivated:
    "Your account has been deactivated. Please contact the administrator.",
};

export function landingFor(user) {
  if (!user) return "/login";
  if (user.role === null) return "/select-role";
  return user.role === "admin" ? "/admin" : "/ai";
}

export default function Login() {
  const { user, flash, setFlash } = useAuth();
  const [params] = useSearchParams();
  const code = params.get("error");

  useEffect(() => {
    return () => setFlash(null);
  }, []);

  useEffect(() => {
    document.title = "Sign in | NEMSU";
  }, []);

  if (user) {
    return <Navigate to={landingFor(user)} replace />;
  }

  const message = MESSAGES[code] || (flash && flash.text);
  const kind = MESSAGES[code] ? "error" : flash && flash.kind;

  const googleLoginUrl = `${API_BASE}/api/auth/google`;

  return (
    <>
      <Header />

      <div className="center-wrap">
        <div className="login-card">
          <img src="/logo.png" alt="NEMSU seal" />

          <h1>NEMSAI</h1>

          <p className="sub">
            NEMSU Tandag Main Campus Assistant
          </p>

          {message && (
            <div className={"flash " + kind} role="alert">
              {message}
            </div>
          )}

          <a
            className="google-btn"
            href={googleLoginUrl}
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 48 48"
              aria-hidden="true"
            >
              <path
                fill="#EA4335"
                d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z"
              />

              <path
                fill="#4285F4"
                d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.6 5.9c4.4-4.1 7-10.1 7-17.6z"
              />

              <path
                fill="#FBBC05"
                d="M10.5 28.7A14.5 14.5 0 0 1 9.5 24c0-1.6.3-3.2.8-4.7l-7.9-6.1A24 24 0 0 0 0 24c0 3.9.9 7.5 2.6 10.8l7.9-6.1z"
              />

              <path
                fill="#34A853"
                d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.6-5.9c-2.1 1.4-4.9 2.3-8.3 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z"
              />
            </svg>

            Continue with Google
          </a>

          <p className="note">
            Use your official NEMSU Google account (@nemsu.edu.ph).
            <br />
            Google handles your sign-in. This site never sees your password.
          </p>
        </div>
      </div>
    </>
  );
}