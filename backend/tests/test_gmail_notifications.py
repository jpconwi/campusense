import base64
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses

import pytest

from app import config
from app.models import Announcement, User
from app.services import gmail_notification_service as gmail


class Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300
        self._payload = payload or {}

    def json(self):
        return self._payload


def configure_gmail(monkeypatch):
    monkeypatch.setattr(config, "GMAIL_CLIENT_ID", "client-id")
    monkeypatch.setattr(config, "GMAIL_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(config, "GMAIL_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setattr(config, "GMAIL_SENDER_EMAIL", "nemsai@gmail.com")


def test_announcement_email_uses_private_bcc_batches(db, monkeypatch):
    configure_gmail(monkeypatch)
    db.add_all([
        User(google_id=f"gmail-user-{index}", name=f"User {index}",
             email=f"user{index}@nemsu.edu.ph", role="student")
        for index in range(51)
    ])
    db.add(User(google_id="gmail-inactive", name="Inactive", email="inactive@nemsu.edu.ph",
                role="student", is_active=False))
    db.add(User(google_id="gmail-pending", name="Pending", email="pending@nemsu.edu.ph",
                role="student", approval_status="Pending"))
    announcement = Announcement(title="Campus update", category="News", body="Read this update.")
    db.add(announcement)
    db.commit()

    requests = []

    def fake_post(url, **kwargs):
        requests.append((url, kwargs))
        return Response(payload={"access_token": "access-token"} if url == gmail.TOKEN_URL else {"id": "sent"})

    monkeypatch.setattr(gmail.httpx, "post", fake_post)
    result = gmail.send_announcement_notification(db, announcement)

    assert result == gmail.NotificationResult("sent", 51)
    assert requests[0][0] == gmail.TOKEN_URL
    send_requests = [kwargs for url, kwargs in requests if url == gmail.SEND_URL]
    assert len(send_requests) == 2
    assert send_requests[0]["headers"] == {"Authorization": "Bearer access-token"}

    first = base64.urlsafe_b64decode(send_requests[0]["json"]["raw"] + "===")
    email = BytesParser(policy=policy.default).parsebytes(first)
    assert str(email["To"]) == "undisclosed-recipients:;"
    assert len(getaddresses([str(email["Bcc"])])) == 50
    assert "inactive@nemsu.edu.ph" not in str(email)
    assert "pending@nemsu.edu.ph" not in str(email)

    second = base64.urlsafe_b64decode(send_requests[1]["json"]["raw"] + "===")
    second_email = BytesParser(policy=policy.default).parsebytes(second)
    assert len(getaddresses([str(second_email["Bcc"])])) == 1


def test_missing_gmail_configuration_skips_delivery(db, monkeypatch):
    monkeypatch.setattr(config, "GMAIL_CLIENT_ID", "")
    monkeypatch.setattr(config, "GMAIL_CLIENT_SECRET", "")
    monkeypatch.setattr(config, "GMAIL_REFRESH_TOKEN", "")
    monkeypatch.setattr(config, "GMAIL_SENDER_EMAIL", "")
    def unexpected_request(*_args, **_kwargs):
        pytest.fail(f"unexpected Gmail request: {_args}, {_kwargs}")

    monkeypatch.setattr(gmail.httpx, "post", unexpected_request)

    result = gmail.send_announcement_notification(
        db, Announcement(title="Campus update", category="News", body="Read this update."))

    assert result == gmail.NotificationResult("not_configured", 0)


def test_record_status_email_is_sent_only_to_record_owner(monkeypatch):
    configure_gmail(monkeypatch)
    requests = []

    def fake_post(url, **kwargs):
        requests.append((url, kwargs))
        return Response(payload={"access_token": "access-token"} if url == gmail.TOKEN_URL else {"id": "sent"})

    monkeypatch.setattr(gmail.httpx, "post", fake_post)
    result = gmail.send_record_status_notification(
        "sam@nemsu.edu.ph", "reports", 42, "Resolved")

    assert result == gmail.NotificationResult("sent", 1)
    send = next(kwargs for url, kwargs in requests if url == gmail.SEND_URL)
    message = BytesParser(policy=policy.default).parsebytes(
        base64.urlsafe_b64decode(send["json"]["raw"] + "==="))
    assert message["From"] == "nemsai@gmail.com"
    assert message["To"] == "sam@nemsu.edu.ph"
    assert message["Bcc"] is None
    assert "Resolved" in message["Subject"]
    assert "http://localhost:8000/reports" in message.get_content()


def test_partial_gmail_configuration_is_reported(db, monkeypatch):
    monkeypatch.setattr(config, "GMAIL_CLIENT_ID", "client-id")
    monkeypatch.setattr(config, "GMAIL_CLIENT_SECRET", "")
    monkeypatch.setattr(config, "GMAIL_REFRESH_TOKEN", "")
    monkeypatch.setattr(config, "GMAIL_SENDER_EMAIL", "")

    with pytest.raises(gmail.GmailNotificationError, match="GMAIL_CLIENT_SECRET"):
        gmail.send_announcement_notification(
            db, Announcement(title="Campus update", category="News", body="Read this update."))


def test_gmail_failure_reports_already_accepted_recipients(db, monkeypatch):
    configure_gmail(monkeypatch)
    db.add_all([
        User(google_id=f"gmail-failure-user-{index}", name=f"User {index}",
             email=f"failure{index}@nemsu.edu.ph", role="student")
        for index in range(51)
    ])
    announcement = Announcement(title="Campus update", category="News", body="Read this update.")
    db.add(announcement)
    db.commit()
    send_count = 0

    def fake_post(url, **_kwargs):
        nonlocal send_count
        assert _kwargs["timeout"] == 20
        if url == gmail.TOKEN_URL:
            return Response(payload={"access_token": "access-token"})
        send_count += 1
        return Response(status_code=403) if send_count == 2 else Response(payload={"id": "sent"})

    monkeypatch.setattr(gmail.httpx, "post", fake_post)
    with pytest.raises(gmail.GmailNotificationError) as raised:
        gmail.send_announcement_notification(db, announcement)

    assert raised.value.delivered_count == 50
    assert raised.value.recipient_count == 51
