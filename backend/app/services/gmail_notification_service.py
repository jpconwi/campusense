"""Send app notifications through Brevo, falling back to the Gmail API on quota limits."""

import base64
import html
from email.message import EmailMessage
from email.utils import formataddr
from typing import NamedTuple

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.models import Announcement, User

TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"
RECIPIENTS_PER_MESSAGE = 50
BREVO_RECIPIENTS_PER_REQUEST = 99


class NotificationResult(NamedTuple):
    status: str
    recipient_count: int


class GmailNotificationError(Exception):
    def __init__(self, message, delivered_count=0, recipient_count=0):
        super().__init__(message)
        self.delivered_count = delivered_count
        self.recipient_count = recipient_count


class BrevoQuotaLimitReached(Exception):
    pass


def _configured():
    if not config.BREVO_API_KEY and not config.BREVO_SENDER_EMAIL:
        return False
    missing = [name for name, value in (
        ("BREVO_API_KEY", config.BREVO_API_KEY),
        ("BREVO_SENDER_EMAIL", config.BREVO_SENDER_EMAIL),
    ) if not value]
    if missing:
        raise GmailNotificationError(
            "Brevo notification setup is incomplete. Set: " + ", ".join(missing) + ".")
    return True


def _require_gmail_fallback_configured():
    oauth_values = {
        "GMAIL_CLIENT_ID": config.GMAIL_CLIENT_ID,
        "GMAIL_CLIENT_SECRET": config.GMAIL_CLIENT_SECRET,
        "GMAIL_REFRESH_TOKEN": config.GMAIL_REFRESH_TOKEN,
    }
    if not any(oauth_values.values()):
        raise GmailNotificationError(
            "Brevo's send limit was reached, but Gmail API fallback is not configured.")
    values = {**oauth_values, "GMAIL_SENDER_EMAIL": config.GMAIL_SENDER_EMAIL}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise GmailNotificationError(
            "Gmail API fallback setup is incomplete. Set: " + ", ".join(missing) + ".")


def _brevo_sender():
    return {"name": config.BREVO_SENDER_NAME, "email": config.BREVO_SENDER_EMAIL}


def _html_lines(value):
    return html.escape(str(value)).replace("\n", "<br>")


def _branded_email_html(preheader, heading, content_html, button_label, button_url):
    logo_url = html.escape(f"{config.PUBLIC_URL}/logo.png", quote=True)
    safe_button_url = html.escape(button_url, quote=True)
    return f"""<!doctype html>
<html lang="en">
  <body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#172b3a;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">{html.escape(preheader)}</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f1f5f9;padding:32px 12px;">
      <tr><td align="center">
        <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="width:100%;max-width:600px;border-collapse:separate;border-spacing:0;">
          <tr><td align="center" style="background:#123247;padding:28px 20px;border-radius:14px 14px 0 0;">
            <img src="{logo_url}" width="68" height="68" alt="NEMSAI logo" style="display:block;width:68px;height:68px;object-fit:contain;border:0;">
            <div style="margin-top:10px;color:#ffffff;font-size:21px;font-weight:700;letter-spacing:1px;">NEMSAI</div>
            <div style="margin-top:4px;color:#c7dce8;font-size:12px;">NEMSU Tandag Campus</div>
          </td></tr>
          <tr><td style="background:#ffffff;padding:32px 30px;border:1px solid #e2e8f0;border-top:0;">
            <h1 style="margin:0 0 18px;font-size:23px;line-height:1.35;color:#123247;">{html.escape(heading)}</h1>
            <div style="font-size:15px;line-height:1.7;color:#334155;">{content_html}</div>
            <p style="margin:26px 0 24px;">
              <a href="{safe_button_url}" style="display:inline-block;background:#087f8c;color:#ffffff;text-decoration:none;font-size:14px;font-weight:700;padding:12px 20px;border-radius:7px;">{html.escape(button_label)}</a>
            </p>
            <p style="margin:0;color:#64748b;font-size:13px;line-height:1.6;">If you have questions, please contact the campus administrators.</p>
          </td></tr>
          <tr><td align="center" style="padding:18px 12px;color:#64748b;font-size:11px;line-height:1.5;">
            Automated notification from NEMSAI.
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


def _email_message(recipient, subject, text_content, html_content):
    message = EmailMessage()
    message["From"] = formataddr((config.BREVO_SENDER_NAME, config.GMAIL_SENDER_EMAIL))
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(text_content)
    message.add_alternative(html_content, subtype="html")
    return message


def _send_gmail_message(message, error_context):
    access_token = _access_token()
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")
    try:
        response = httpx.post(
            SEND_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
            timeout=20,
        )
    except httpx.HTTPError as error:
        raise GmailNotificationError(f"Could not reach the Gmail API to send {error_context}.") from error
    if not response.is_success:
        raise GmailNotificationError(
            f"The Gmail API could not send {error_context} (HTTP {response.status_code}).")


def _send_single_email(recipient, subject, text_content, html_content, error_context):
    if not _configured():
        return NotificationResult("not_configured", 0)
    payload = {
        "sender": _brevo_sender(),
        "to": [{"email": recipient}],
        "subject": subject,
        "textContent": text_content,
        "htmlContent": html_content,
    }
    try:
        _send_brevo(payload)
    except BrevoQuotaLimitReached:
        print(f"BREVO QUOTA REACHED: using Gmail API fallback for {error_context}.")
        message = _email_message(recipient, subject, text_content, html_content)
        _send_gmail_message(message, error_context)
    return NotificationResult("sent", 1)


def _brevo_error_payload(response):
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _brevo_quota_limit_reached(response, payload):
    if response.status_code == 429:
        return True
    code = str(payload.get("code") or "").lower().replace("-", "_")
    message = str(payload.get("message") or "").lower()
    return (code in ("not_enough_credits", "rate_limit", "rate_limit_exceeded")
            or "insufficient credits" in message
            or "quota exceeded" in message
            or "daily limit" in message
            or "rate limit" in message)


def _send_brevo(payload):
    try:
        response = httpx.post(
            BREVO_SEND_URL,
            headers={"api-key": config.BREVO_API_KEY},
            json=payload,
            timeout=20,
        )
    except httpx.HTTPError as error:
        raise GmailNotificationError(
            "Could not reach Brevo; Gmail fallback was not attempted because delivery "
            "outcome is unknown.") from error
    if response.is_success:
        return
    error_payload = _brevo_error_payload(response)
    if _brevo_quota_limit_reached(response, error_payload):
        raise BrevoQuotaLimitReached
    code = str(error_payload.get("code") or "unknown")
    raise GmailNotificationError(
        f"Brevo could not send the email (HTTP {response.status_code}, code {code}).")


def _response_json(response, operation):
    try:
        payload = response.json()
    except ValueError as error:
        raise GmailNotificationError(f"The Gmail {operation} response was invalid.") from error
    if not isinstance(payload, dict):
        raise GmailNotificationError(f"The Gmail {operation} response was invalid.")
    return payload


def _access_token():
    _require_gmail_fallback_configured()
    try:
        response = httpx.post(TOKEN_URL, data={
            "client_id": config.GMAIL_CLIENT_ID,
            "client_secret": config.GMAIL_CLIENT_SECRET,
            "refresh_token": config.GMAIL_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        }, timeout=20)
    except httpx.HTTPError as error:
        raise GmailNotificationError("Could not reach Google to authorize the Gmail sender.") from error
    if not response.is_success:
        raise GmailNotificationError(
            f"Google could not authorize the Gmail sender (HTTP {response.status_code}).")
    token = _response_json(response, "authorization").get("access_token")
    if not isinstance(token, str) or not token:
        raise GmailNotificationError("Google did not return a Gmail access token.")
    return token


def _message_obj(announcement, recipients):
    message = EmailMessage()
    message["From"] = formataddr((config.BREVO_SENDER_NAME, config.GMAIL_SENDER_EMAIL))
    message["To"] = "undisclosed-recipients:;"
    message["Bcc"] = ", ".join(recipients)
    message["Subject"] = f"[NEMSU Announcement] {announcement.title}"
    message.set_content(_announcement_content(announcement))
    message.add_alternative(_announcement_html(announcement), subtype="html")
    return message


def _message_raw(announcement, recipients):
    return base64.urlsafe_b64encode(_message_obj(announcement, recipients).as_bytes()).decode("ascii").rstrip("=")


def _announcement_content(announcement):
    dates = []
    if announcement.start_date:
        dates.append(f"Show from: {announcement.start_date.isoformat()}")
    if announcement.end_date:
        dates.append(f"Until: {announcement.end_date.isoformat()}")
    date_text = "\n" + "\n".join(dates) if dates else ""
    return (
        f"{announcement.title}\n"
        f"Category: {announcement.category}\n\n"
        f"{announcement.body}"
        f"{date_text}\n\n"
        f"View campus announcements: {config.PUBLIC_URL}/notifications\n"
    )


def _announcement_html(announcement):
    dates = []
    if announcement.start_date:
        dates.append(f"<p><strong>Show from:</strong> {_html_lines(announcement.start_date.isoformat())}</p>")
    if announcement.end_date:
        dates.append(f"<p><strong>Until:</strong> {_html_lines(announcement.end_date.isoformat())}</p>")
    content = (
        f"<p><strong>Category:</strong> {_html_lines(announcement.category)}</p>"
        f"<p>{_html_lines(announcement.body)}</p>"
        + "".join(dates)
    )
    return _branded_email_html(
        "A new campus announcement has been posted.",
        announcement.title,
        content,
        "View announcements",
        f"{config.PUBLIC_URL}/notifications",
    )


def _announcement_brevo_payload(announcement, recipients):
    return {
        "sender": _brevo_sender(),
        "subject": f"[NEMSU Announcement] {announcement.title}",
        "textContent": _announcement_content(announcement),
        "htmlContent": _announcement_html(announcement),
        "messageVersions": [
            {"to": [{"email": recipient}]} for recipient in recipients
        ],
    }


def _send_gmail_announcement(announcement, recipients, already_delivered=0, total_recipients=None):
    total_recipients = total_recipients if total_recipients is not None else len(recipients)
    access_token = _access_token()
    delivered_count = already_delivered
    for offset in range(0, len(recipients), RECIPIENTS_PER_MESSAGE):
        batch = recipients[offset:offset + RECIPIENTS_PER_MESSAGE]
        try:
            response = httpx.post(
                SEND_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": _message_raw(announcement, batch)},
                timeout=20,
            )
        except httpx.HTTPError as error:
            raise GmailNotificationError(
                "Could not reach the Gmail API to send announcement email.",
                delivered_count, total_recipients) from error
        if not response.is_success:
            raise GmailNotificationError(
                f"The Gmail API could not send announcement email (HTTP {response.status_code}).",
                delivered_count, total_recipients)
        delivered_count += len(batch)
    return NotificationResult("sent", delivered_count)


def send_announcement_notification(db: Session, announcement: Announcement):
    """Email all active, approved accounts privately; use Gmail if Brevo hits its limit."""
    if not _configured():
        return NotificationResult("not_configured", 0)

    recipients = db.execute(
        select(User.email)
        .where(User.is_active.is_(True), User.approval_status == "Approved")
        .order_by(User.id)
    ).scalars().all()
    if not recipients:
        return NotificationResult("no_recipients", 0)

    delivered_count = 0
    for offset in range(0, len(recipients), BREVO_RECIPIENTS_PER_REQUEST):
        batch = recipients[offset:offset + BREVO_RECIPIENTS_PER_REQUEST]
        try:
            _send_brevo(_announcement_brevo_payload(announcement, batch))
        except BrevoQuotaLimitReached:
            remaining = recipients[offset:]
            print(f"BREVO QUOTA REACHED: Gmail API fallback for {len(remaining)} announcement recipient(s).")
            try:
                return _send_gmail_announcement(
                    announcement, remaining, delivered_count, len(recipients))
            except GmailNotificationError as error:
                raise GmailNotificationError(
                    str(error), error.delivered_count or delivered_count, len(recipients)) from error
        except GmailNotificationError as error:
            raise GmailNotificationError(
                str(error), delivered_count, len(recipients)) from error
        delivered_count += len(batch)
    return NotificationResult("sent", delivered_count)


def send_record_status_notification(recipient_email, kind, record_id, status, update_message=None):
    """Email the record owner about a status change or a direct admin update."""
    pages = {
        "concerns": ("concern", "concerns"),
        "reports": ("report", "reports"),
        "reservations": ("reservation", "reservations"),
    }
    if kind not in pages:
        raise ValueError(f"Unsupported record kind: {kind}")
    if not recipient_email:
        raise ValueError("A recipient email is required.")
    label, page = pages[kind]
    subject = (f"[NEMSAI] Admin update about your {label} #{record_id}"
               if update_message else f"[NEMSAI] Your {label} #{record_id}: {status}")
    content = (
        f"Your {label} (#{record_id}) status is now: {status}.\n\n"
    )
    details_html = f"<p>Your {label} <strong>#{record_id}</strong> status is now <strong>{_html_lines(status)}</strong>.</p>"
    heading = f"Update about your {label} #{record_id}"
    if update_message:
        content += f"Administrator update:\n{update_message}\n\n"
        details_html += f"<p><strong>Administrator update</strong></p><p>{_html_lines(update_message)}</p>"
        heading = f"A new administrator update is available"
    content += f"View your {label}: {config.PUBLIC_URL}/{page}\n"
    html_content = _branded_email_html(
        f"An administrator updated your {label}.",
        heading,
        details_html,
        f"View your {label}",
        f"{config.PUBLIC_URL}/{page}",
    )
    return _send_single_email(
        recipient_email, subject, content, html_content, f"{label} notification")


def send_report_decision_notification(recipient_email, kind, record_id, decision, note=None):
    if kind not in ("reports", "concerns"):
        raise ValueError(f"Unsupported report kind: {kind}")
    if decision not in ("Accepted", "Rejected"):
        raise ValueError(f"Unsupported report decision: {decision}")
    if not recipient_email:
        raise ValueError("A recipient email is required.")

    label, page = ("report", "reports") if kind == "reports" else ("concern", "concerns")
    subject = f"[NEMSAI] Your {label} #{record_id} was {decision.lower()}"
    content = (
        f"The Super Admin has {decision.lower()} your {label} (#{record_id}).\n"
        f"Review decision: {decision}\n"
    )
    details_html = (
        f"<p>The Super Admin has <strong>{decision.lower()}</strong> your "
        f"{label} <strong>#{record_id}</strong>.</p>"
    )
    if note:
        content += f"\nReview note:\n{note}\n"
        details_html += f"<p><strong>Review note</strong></p><p>{_html_lines(note)}</p>"
    content += f"\nView your {label}: {config.PUBLIC_URL}/{page}\n"
    html_content = _branded_email_html(
        f"The Super Admin reviewed your {label}.",
        f"Your {label} was {decision.lower()}",
        details_html,
        f"View your {label}",
        f"{config.PUBLIC_URL}/{page}",
    )
    return _send_single_email(
        recipient_email, subject, content, html_content, f"{label} decision notification")


def send_account_decision_notification(recipient_email, name, decision, reason=None):
    if decision not in ("Approved", "Rejected"):
        raise ValueError(f"Unsupported account decision: {decision}")
    if not recipient_email:
        raise ValueError("A recipient email is required.")

    approved = decision == "Approved"
    subject = (f"[NEMSAI] Your account has been {decision.lower()}")
    content = (
        f"Hello {name},\n\n"
        + ("Your NEMSAI account has been approved. You can now sign in.\n"
           if approved else "Your NEMSAI account registration was not approved.\n")
    )
    details_html = (
        f"<p>Hello {_html_lines(name)},</p>"
        + ("<p>Your NEMSAI account has been approved. You can now sign in.</p>"
           if approved else "<p>Your NEMSAI account registration was not approved.</p>")
    )
    if reason:
        content += f"\nReason: {reason}\n"
        details_html += f"<p><strong>Reason</strong></p><p>{_html_lines(reason)}</p>"
    content += f"\nSign in: {config.PUBLIC_URL}/login\n"
    html_content = _branded_email_html(
        f"Your NEMSAI account decision is {decision.lower()}.",
        f"Account {decision.lower()}",
        details_html,
        "Sign in to NEMSAI" if approved else "Visit NEMSAI",
        f"{config.PUBLIC_URL}/login",
    )
    return _send_single_email(
        recipient_email, subject, content, html_content, "account decision notification")


def send_account_welcome_notification(recipient_email, name):
    if not recipient_email:
        raise ValueError("A recipient email is required.")
    subject = "[NEMSAI] Welcome to NEMSAI"
    content = (
        f"Welcome to NEMSAI, {name}!\n\n"
        "Your registration has been approved and your account is ready. You can now sign in "
        "with your Google account and ask NEMSAI for NEMSU campus information, student services, "
        "or help with campus concerns.\n\n"
        f"Sign in: {config.PUBLIC_URL}/login\n"
    )
    details_html = (
        f"<p>Welcome to NEMSAI, {_html_lines(name)}!</p>"
        "<p>Your registration has been approved and your account is ready. Sign in with your "
        "Google account and feel free to use NEMSAI for campus information, student services, "
        "and campus concerns.</p>"
    )
    html_content = _branded_email_html(
        "Your NEMSAI account is ready.", "Welcome to NEMSAI", details_html,
        "Sign in to NEMSAI", f"{config.PUBLIC_URL}/login")
    return _send_single_email(
        recipient_email, subject, content, html_content, "account welcome notification")


def send_account_pending_notification(recipient_email, name):
    if not recipient_email:
        raise ValueError("A recipient email is required.")
    subject = "[NEMSAI] Your account is under review"
    content = (
        f"Hello {name},\n\n"
        "Your NEMSAI account registration is under review by the campus administrators. "
        "You cannot sign in until it is approved. We will email you when a decision is made.\n\n"
        f"Registration status: {config.PUBLIC_URL}/login\n"
    )
    details_html = (
        f"<p>Hello {_html_lines(name)},</p>"
        "<p>Your NEMSAI account registration is under review by the campus administrators. "
        "You cannot sign in until it is approved. We will email you when a decision is made.</p>"
    )
    html_content = _branded_email_html(
        "Your registration is waiting for administrator review.", "Account under review",
        details_html, "View NEMSAI", f"{config.PUBLIC_URL}/login")
    return _send_single_email(
        recipient_email, subject, content, html_content, "account pending notification")


def send_pending_account_review_notification(name, recipient_email, registration_type, user_id):
    if not config.ACCOUNT_REVIEW_EMAIL:
        raise ValueError("An account review email is required.")
    review_url = f"{config.PUBLIC_URL}/admin/accounts"
    subject = "[NEMSAI] 1 account needs approval"
    registration_type = str(registration_type or "student").strip().title()
    details = (
        f"<p>A new {html.escape(registration_type)} account needs manual approval.</p>"
        f"<p><strong>Applicant:</strong> {_html_lines(name)}<br>"
        f"<strong>Email:</strong> {_html_lines(recipient_email)}<br>"
        f"<strong>Account ID:</strong> {int(user_id)}</p>"
    )
    content = (
        "A new account needs manual approval.\n\n"
        f"Applicant: {name}\nEmail: {recipient_email}\n"
        f"Account type: {registration_type}\nAccount ID: {int(user_id)}\n\n"
        f"Review pending accounts: {review_url}\n"
    )
    html_content = _branded_email_html(
        "A new NEMSAI registration is waiting for review.",
        "New account awaiting approval", details, "Review pending accounts", review_url)
    return _send_single_email(
        config.ACCOUNT_REVIEW_EMAIL, subject, content, html_content,
        "pending account review notification")


def send_feedback_receipt(recipient_email, feedback_id, area, feedback_type):
    if not recipient_email:
        raise ValueError("A recipient email is required.")
    subject = f"[NEMSAI] We received your feedback #{feedback_id}"
    content = (
        f"Thank you for your feedback. It has been sent to the campus administrators for review.\n\n"
        f"Reference: #{feedback_id}\nArea: {area}\nCategory: {feedback_type}\n\n"
        f"View your feedback: {config.PUBLIC_URL}/feedback\n"
    )
    details_html = (
        "<p>Thank you for helping improve the campus. Your feedback has been received "
        "and sent to the administrators for review.</p>"
        f"<p><strong>Reference:</strong> #{feedback_id}<br>"
        f"<strong>Area:</strong> {_html_lines(area)}<br>"
        f"<strong>Category:</strong> {_html_lines(feedback_type)}</p>"
    )
    html_content = _branded_email_html(
        "Your feedback was received by the campus administrators.",
        "Feedback received",
        details_html,
        "View my feedback",
        f"{config.PUBLIC_URL}/feedback",
    )
    return _send_single_email(
        recipient_email, subject, content, html_content, "feedback receipt")


def notify_record_owner(recipient_email, kind, record_id, status):
    """Keep email failures from reversing a saved submission or status change."""
    try:
        return send_record_status_notification(recipient_email, kind, record_id, status)
    except GmailNotificationError as error:
        print("EMAIL RECORD NOTIFICATION ERROR:", repr(error))
        return NotificationResult("failed", 0)


def notify_report_decision(recipient_email, kind, record_id, decision, note=None):
    try:
        return send_report_decision_notification(
            recipient_email, kind, record_id, decision, note)
    except GmailNotificationError as error:
        print("EMAIL REPORT DECISION ERROR:", repr(error))
        return NotificationResult("failed", 0)


def notify_record_update(recipient_email, kind, record_id, status, update_message):
    """Email a saved administrator update without undoing the database change on failure."""
    try:
        return send_record_status_notification(
            recipient_email, kind, record_id, status, update_message=update_message)
    except GmailNotificationError as error:
        print("EMAIL RECORD UPDATE ERROR:", repr(error))
        return NotificationResult("failed", 0)


def notify_account_decision(recipient_email, name, decision, reason=None):
    try:
        return send_account_decision_notification(
            recipient_email, name, decision, reason)
    except GmailNotificationError as error:
        print("EMAIL ACCOUNT DECISION ERROR:", repr(error))
        return NotificationResult("failed", 0)


def notify_account_welcome(recipient_email, name):
    try:
        return send_account_welcome_notification(recipient_email, name)
    except GmailNotificationError as error:
        print("EMAIL ACCOUNT WELCOME ERROR:", repr(error))
        return NotificationResult("failed", 0)


def notify_account_pending(recipient_email, name):
    try:
        return send_account_pending_notification(recipient_email, name)
    except GmailNotificationError as error:
        print("EMAIL ACCOUNT PENDING ERROR:", repr(error))
        return NotificationResult("failed", 0)


def notify_pending_account_review(name, recipient_email, registration_type, user_id):
    try:
        return send_pending_account_review_notification(
            name, recipient_email, registration_type, user_id)
    except GmailNotificationError as error:
        print("EMAIL PENDING ACCOUNT REVIEW ERROR:", repr(error))
        return NotificationResult("failed", 0)


def notify_feedback_submission(recipient_email, feedback_id, area, feedback_type):
    try:
        return send_feedback_receipt(recipient_email, feedback_id, area, feedback_type)
    except GmailNotificationError as error:
        print("EMAIL FEEDBACK RECEIPT ERROR:", repr(error))
        return NotificationResult("failed", 0)


def update_notification_notice(result):
    if result.status == "sent":
        return " The update was emailed to the reporter."
    if result.status == "not_configured":
        return " The update was saved, but Brevo is not configured so no email was sent."
    if result.status == "failed":
        return " The update was saved, but the reporter email could not be sent."
    raise ValueError(f"Unknown Gmail notification status: {result.status}")


def notification_notice(result):
    if result.status == "sent":
        return " A notification email was sent."
    if result.status == "not_configured":
        return " A notification email was not sent because Brevo is not configured."
    if result.status == "failed":
        return " The notification email could not be sent."
    raise ValueError(f"Unknown Gmail notification status: {result.status}")
