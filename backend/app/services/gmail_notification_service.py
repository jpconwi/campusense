"""Send announcement emails through the Gmail API using a dedicated OAuth sender."""

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
RECIPIENTS_PER_MESSAGE = 50


class NotificationResult(NamedTuple):
    status: str
    recipient_count: int


class GmailNotificationError(Exception):
    def __init__(self, message, delivered_count=0, recipient_count=0):
        super().__init__(message)
        self.delivered_count = delivered_count
        self.recipient_count = recipient_count


def _configured():
    oauth_values = {
        "GMAIL_CLIENT_ID": config.GMAIL_CLIENT_ID,
        "GMAIL_CLIENT_SECRET": config.GMAIL_CLIENT_SECRET,
        "GMAIL_REFRESH_TOKEN": config.GMAIL_REFRESH_TOKEN,
    }
    if not any(oauth_values.values()):
        return False
    values = {**oauth_values, "GMAIL_SENDER_EMAIL": config.GMAIL_SENDER_EMAIL}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise GmailNotificationError(
            "Gmail notification setup is incomplete. Set: " + ", ".join(missing) + ".")
    return True


def _response_json(response, operation):
    try:
        payload = response.json()
    except ValueError as error:
        raise GmailNotificationError(f"The Gmail {operation} response was invalid.") from error
    if not isinstance(payload, dict):
        raise GmailNotificationError(f"The Gmail {operation} response was invalid.")
    return payload


def _access_token():
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


def _message_raw(announcement, recipients):
    message = EmailMessage()
    message["From"] = config.GMAIL_SENDER_EMAIL
    message["To"] = "undisclosed-recipients:;"
    message["Bcc"] = ", ".join(recipients)
    message["Subject"] = f"[NEMSU Announcement] {announcement.title}"
    dates = []
    if announcement.start_date:
        dates.append(f"Show from: {announcement.start_date.isoformat()}")
    if announcement.end_date:
        dates.append(f"Until: {announcement.end_date.isoformat()}")
    date_text = "\n" + "\n".join(dates) if dates else ""
    message.set_content(
        f"{announcement.title}\n"
        f"Category: {announcement.category}\n\n"
        f"{announcement.body}"
        f"{date_text}\n\n"
        f"View campus announcements: {config.PUBLIC_URL}/notifications\n"
    )
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")


def send_announcement_notification(db: Session, announcement: Announcement):
    """Email all active, approved accounts; recipients are hidden from one another."""
    if not _configured():
        return NotificationResult("not_configured", 0)

    recipients = db.execute(
        select(User.email)
        .where(User.is_active.is_(True), User.approval_status == "Approved")
        .order_by(User.id)
    ).scalars().all()
    if not recipients:
        return NotificationResult("no_recipients", 0)

    access_token = _access_token()
    delivered_count = 0
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
                delivered_count, len(recipients)) from error
        if not response.is_success:
            raise GmailNotificationError(
                f"The Gmail API could not send announcement email (HTTP {response.status_code}).",
                delivered_count, len(recipients))
        delivered_count += len(batch)

    return NotificationResult("sent", delivered_count)


def send_record_status_notification(recipient_email, kind, record_id, status):
    """Email one account after one of its records is submitted or changes status."""
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
    message["Subject"] = f"[NEMSAI] Your {label} #{record_id} is {status}"
    message.set_content(
        f"Your {label} (#{record_id}) status is now: {status}.\n\n"
        f"View your {label}: {config.PUBLIC_URL}/{page}\n"
    )
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")

    try:
        response = httpx.post(
            SEND_URL,
            headers={"Authorization": f"Bearer {_access_token()}"},
            json={"raw": raw},
            timeout=20,
        )
    except httpx.HTTPError as error:
        raise GmailNotificationError(
            "Could not reach the Gmail API to send a record status email.") from error
    if not response.is_success:
        raise GmailNotificationError(
            f"The Gmail API could not send a record status email (HTTP {response.status_code}).")
    return NotificationResult("sent", 1)


def notify_record_owner(recipient_email, kind, record_id, status):
    """Keep email failures from reversing a saved submission or status change."""
    try:
        return send_record_status_notification(recipient_email, kind, record_id, status)
    except GmailNotificationError as error:
        print("GMAIL RECORD NOTIFICATION ERROR:", repr(error))
        return NotificationResult("failed", 0)


def notification_notice(result):
    if result.status == "sent":
        return " A status email was sent."
    if result.status == "not_configured":
        return " A status email was not sent because Gmail is not configured."
    if result.status == "failed":
        return " The status email could not be sent."
    raise ValueError(f"Unknown Gmail notification status: {result.status}")
