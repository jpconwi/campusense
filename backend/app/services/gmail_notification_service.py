"""Send app notifications through Brevo, falling back to the Gmail API on quota limits."""

import base64
from email.message import EmailMessage
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
    message["From"] = config.GMAIL_SENDER_EMAIL
    message["To"] = "undisclosed-recipients:;"
    message["Bcc"] = ", ".join(recipients)
    message["Subject"] = f"[NEMSU Announcement] {announcement.title}"
    message.set_content(_announcement_content(announcement))
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


def _announcement_brevo_payload(announcement, recipients):
    return {
        "sender": _brevo_sender(),
        "subject": f"[NEMSU Announcement] {announcement.title}",
        "textContent": _announcement_content(announcement),
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
        "feedback": ("feedback item", "feedback"),
        "reservations": ("reservation", "reservations"),
    }
    if kind not in pages:
        raise ValueError(f"Unsupported record kind: {kind}")
    if not recipient_email:
        raise ValueError("A recipient email is required.")
    if not _configured():
        return NotificationResult("not_configured", 0)

    label, page = pages[kind]
    message = EmailMessage()
    message["From"] = config.GMAIL_SENDER_EMAIL
    message["To"] = recipient_email
    message["Subject"] = (f"[NEMSAI] Update about your {label} #{record_id}"
                          if update_message else f"[NEMSAI] Your {label} #{record_id} is {status}")
    content = (
        f"Your {label} (#{record_id}) status is now: {status}.\n\n"
    )
    if update_message:
        content += f"Administrator update:\n{update_message}\n\n"
    content += f"View your {label}: {config.PUBLIC_URL}/{page}\n"
    message.set_content(content)
    payload = {
        "sender": _brevo_sender(),
        "to": [{"email": recipient_email}],
        "subject": str(message["Subject"]),
        "textContent": message.get_content(),
    }
    try:
        _send_brevo(payload)
    except BrevoQuotaLimitReached:
        print("BREVO QUOTA REACHED: using Gmail API fallback for a record notification.")
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")
        access_token = _access_token()
        try:
            response = httpx.post(
                SEND_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw},
                timeout=20,
            )
        except httpx.HTTPError as error:
            raise GmailNotificationError(
                "Could not reach the Gmail API for fallback delivery.") from error
        if not response.is_success:
            raise GmailNotificationError(
                f"The Gmail API fallback could not send the email (HTTP {response.status_code}).")
    return NotificationResult("sent", 1)


def notify_record_owner(recipient_email, kind, record_id, status):
    """Keep email failures from reversing a saved submission or status change."""
    try:
        return send_record_status_notification(recipient_email, kind, record_id, status)
    except GmailNotificationError as error:
        print("EMAIL RECORD NOTIFICATION ERROR:", repr(error))
        return NotificationResult("failed", 0)


def notify_record_update(recipient_email, kind, record_id, status, update_message):
    """Email a saved administrator update without undoing the database change on failure."""
    try:
        return send_record_status_notification(
            recipient_email, kind, record_id, status, update_message=update_message)
    except GmailNotificationError as error:
        print("EMAIL RECORD UPDATE ERROR:", repr(error))
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
        return " A status email was sent."
    if result.status == "not_configured":
        return " A status email was not sent because Brevo is not configured."
    if result.status == "failed":
        return " The status email could not be sent."
    raise ValueError(f"Unknown Gmail notification status: {result.status}")
