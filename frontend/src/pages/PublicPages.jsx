import { useEffect } from "react";
import { Link } from "react-router-dom";
import { Header } from "../components/Layout.jsx";

const SUPPORT_EMAIL = "jpconwi2005@gmail.com";

function PublicShell({ title, children }) {
  useEffect(() => {
    document.title = `${title} | NEMSAI`;
  }, [title]);

  return (
    <>
      <Header><Link className="header-btn" to="/login">Sign in</Link></Header>
      <main className="public-page">
        {children}
        <footer className="public-footer" aria-label="Public information links">
          <Link to="/about">About NEMSAI</Link>
          <Link to="/privacy-policy">Privacy Policy</Link>
          <Link to="/terms-of-service">Terms of Service</Link>
          <a href={`mailto:${SUPPORT_EMAIL}`}>Contact</a>
        </footer>
      </main>
    </>
  );
}

function PolicySection({ title, children }) {
  return (
    <section className="public-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

export function PublicHome() {
  return (
    <PublicShell title="About">
      <section className="public-hero">
        <p className="public-eyebrow">NORTH EASTERN MINDANAO STATE UNIVERSITY</p>
        <h2>NEMSAI</h2>
        <p className="public-lead">NEMSU Tandag Main Campus Assistant</p>
        <p>
          NEMSAI helps the NEMSU Tandag Main Campus community find campus information,
          ask questions, read announcements, and submit campus concerns, reports, feedback,
          and other available requests.
        </p>
        <Link className="btn" to="/login">Continue to NEMSAI</Link>
      </section>
      <section className="public-section">
        <h3>How the service works</h3>
        <p>
          Sign in with Google to use the available features. Depending on your account and
          approval, you can use the assistant, submit records, and receive email updates
          about announcements and your submissions.
        </p>
        <p>
          Read our <Link to="/privacy-policy">Privacy Policy</Link> to learn what information
          the service uses, and our <Link to="/terms-of-service">Terms of Service</Link>
          before signing in.
        </p>
      </section>
    </PublicShell>
  );
}

export function PrivacyPolicy() {
  return (
    <PublicShell title="Privacy Policy">
      <article className="public-document">
        <h2>Privacy Policy</h2>
        <p className="public-muted">Last updated: November 22, 2026</p>
        <p>
          NORTH EASTERN MINDANAO STATE UNIVERSITY operates NEMSAI, the NEMSU Tandag Main
          Campus Assistant. This policy explains how NEMSAI handles information when you
          use the service.
        </p>

        <PolicySection title="Information the service uses">
          <ul>
            <li>
              <strong>Sign-in and account information:</strong> Google account name, email
              address, and account identifier; your NEMSAI role and, where applicable,
              student or instructor registration details such as department and student ID.
              Google handles your password; NEMSAI does not receive it.
            </li>
            <li>
              <strong>Registration and verification materials:</strong> documents or images
              you choose to submit, which may include a school ID, certificate of
              registration, or selfie for account review.
            </li>
            <li>
              <strong>Service content:</strong> questions and chat messages, reports,
              concerns, feedback, reservations or availability requests, attached photos,
              and related status or administrative responses.
            </li>
            <li>
              <strong>Basic service activity:</strong> account, sign-in, submission, and
              update timestamps needed to operate, secure, and administer the service.
            </li>
          </ul>
        </PolicySection>

        <PolicySection title="How information is used and shared">
          <p>
            Information is used to sign you in, review account eligibility, provide NEMSAI
            features, route and manage submissions, send requested service emails, protect
            the service, and meet university or legal obligations. Authorized university
            personnel may review account information and submissions as needed to perform
            their duties.
          </p>
          <p>
            To generate answers or analyze a submitted report photo, the text or image you
            provide may be sent to the AI service provider configured for NEMSAI. Depending
            on the deployment configuration, providers may include Hugging Face, Cloudflare,
            Groq, Google, or OpenRouter. Those providers process data under their own terms
            and privacy practices.
          </p>
          <p>
            NEMSAI uses Google sign-in for basic account identity. It does not access your
            Gmail inbox. The separate Gmail API connection is authorized by the NEMSAI
            sending account, <strong>nemsai@gmail.com</strong>, and is used to send
            announcements and updates about submissions. Recipient email addresses and the
            relevant announcement or status are used to deliver those messages.
          </p>
          <p>
            NEMSAI also relies on hosting, database, and file-storage services configured
            by its operators. If private Cloudinary storage is enabled, uploaded images or
            registration documents may be stored there. Information is shared with these
            providers only as needed to operate the service.
          </p>
        </PolicySection>

        <PolicySection title="Retention">
          <p>
            Saved chat history is automatically deleted after three days by default.
            Unsubmitted photo-report drafts are automatically deleted after 24 hours by
            default.
            Account information, verification materials, and submitted university records
            may be kept for as long as needed to operate the service and satisfy applicable
            university recordkeeping or legal requirements. Retention periods may vary by
            record type.
          </p>
        </PolicySection>

        <PolicySection title="Your choices and requests">
          <p>
            You can choose what to include in a chat or submission and may delete your
            saved chats through the service. To ask about access, correction, or deletion of
            account information or a submission, contact{" "}
            <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>. The university may need
            to retain records where required for administration, safety, or legal reasons.
          </p>
        </PolicySection>

        <PolicySection title="Security and changes">
          <p>
            NEMSAI uses account permissions and other safeguards intended to protect
            information. No online service can guarantee absolute security. This policy may
            be updated when the service or its data practices change; the current version
            will be posted on this page.
          </p>
        </PolicySection>
      </article>
    </PublicShell>
  );
}

export function TermsOfService() {
  return (
    <PublicShell title="Terms of Service">
      <article className="public-document">
        <h2>Terms of Service</h2>
        <p className="public-muted">Last updated: November 22, 2026</p>
        <p>
          These terms apply to your use of NEMSAI, the NEMSU Tandag Main Campus Assistant,
          operated by NORTH EASTERN MINDANAO STATE UNIVERSITY. By using NEMSAI, you agree
          to follow these terms and applicable university policies.
        </p>

        <PolicySection title="Accounts and responsible use">
          <ul>
            <li>Use an account and provide information that is accurate and belongs to you.</li>
            <li>
              Submit only information, documents, and images you are authorized to provide.
              Do not upload another person's sensitive information without permission.
            </li>
            <li>
              Do not misuse the service, interfere with its operation, attempt unauthorized
              access, or use it to submit unlawful, threatening, or deliberately misleading
              material.
            </li>
            <li>
              Some features require an eligible account or university approval. Access may
              be limited or suspended in accordance with university rules.
            </li>
          </ul>
        </PolicySection>

        <PolicySection title="Submissions and assistant responses">
          <p>
            Submitting a concern, report, feedback, reservation, or other request does not
            guarantee approval, a particular response, or a particular resolution. An
            authorized university staff member reviews submissions according to the
            applicable process.
          </p>
          <p>
            NEMSAI may use automated AI services to answer questions or assist with
            analyzing submitted content. AI-generated information may be incomplete or
            inaccurate and is not an official university decision or substitute for
            confirmation from the responsible university office. Do not rely on NEMSAI for
            emergencies; contact the appropriate emergency or campus office directly.
          </p>
        </PolicySection>

        <PolicySection title="Service availability and third-party services">
          <p>
            Features may change or be temporarily unavailable. Google sign-in, email
            delivery, hosting, storage, and AI features may rely on third-party services
            governed by their own terms. Your use of NEMSAI is also subject to the{" "}
            <Link to="/privacy-policy">Privacy Policy</Link>.
          </p>
        </PolicySection>

        <PolicySection title="Contact">
          <p>
            Questions about these terms may be sent to{" "}
            <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>.
          </p>
        </PolicySection>
      </article>
    </PublicShell>
  );
}
