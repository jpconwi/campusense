import { Link } from "react-router-dom";
import { Header } from "../components/Layout.jsx";

export default function NotFound({ message = "That page was not found." }) {
  return (
    <>
      <Header />
      <div className="page">
        <h2 className="page-title">404</h2>
        <p className="page-intro">{message}</p>
        <p><Link className="btn" to="/">Go to the home page</Link></p>
      </div>
    </>
  );
}
