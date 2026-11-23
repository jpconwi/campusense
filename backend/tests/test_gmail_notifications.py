import base64
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses

import pytest

from app import config
from app.models import Announcement, User
from app.services import gmail_notification_service as notifications


class Response:
    def __init__(self, status_code=201, payload=None):
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300
        self._payload = payload or {}

    def json(self):
        return self._payload


def configure_brevo(monkeypatch, gmail_fallback=False):
    monkeypatch.setattr(config, "BREVO_API_KEY", "brevo-api-key")
    monkeypatch.setattr(config, "BREVO_SENDER_EMAIL", "notifications@example.com")
    monkeypatch.setattr(config, "BREVO_SENDER_NAME", "NEMSAI")
    monkeypatch.setattr(config, "GMAIL_CLIENT_ID", "client-id" if gmail_fallback else "")
    monkeypatch.setattr(config, "GMAIL_CLIENT_SECRET", "client-secret" if gmail_fallback else "")
    monkeypatch.setattr(config, "GMAIL_REFRESH_TOKEN", "refresh-token" if gmail_fallback else "")
    monkeypatch.setattr(config, "GMAIL_SENDER_EMAIL", "fallback@gmail.com")


def test_announcement_email_uses_private_brevo_message_versions(db, monkeypatch):
    configure_brevo(monkeypatch)
    db.add_all([
        User(google_id=f"brevo-user-{index}", name=f"User {index}",
             email=f"user{index}@nemsu.edu.ph", role="student")
        for index in range(51)
    ])
    db.add(User(google_id="brevo-inactive", name="Inactive", email="inactive@nemsu.edu.ph",
                role="student", is_active=False))
    db.add(User(google_id="brevo-pending", name="Pending", email="pending@nemsu.edu.ph",
                role="student", approval_status="Pending"))
    announcement = Announcement(title="Campus update", category="News", body="Read this update.")
    db.add(announcement)
    db.commit()
    requests = []

    def fake_post(url, **kwargs):
        requests.append((url, kwargs))
        return Response(payload={"messageId": "sent"})

    monkeypatch.setattr(notifications.httpx, "post", fake_post)
    result = notifications.send_announcement_notification(db, announcement)

    assert result == notifications.NotificationResult("sent", 51)
    assert len(requests) == 1
    url, request = requests[0]
    assert url == notifications.BREVO_SEND_URL
    assert request["headers"] == {"api-key": "brevo-api-key"}
    versions = request["json"]["messageVersions"]
    assert len(versions) == 51
    assert all(len(version["to"]) == 1 for version in versions)
    assert "inactive@nemsu.edu.ph" not in str(request["json"])
    assert "pending@nemsu.edu.ph" not in str(request["json"])


def test_missing_brevo_configuration_skips_delivery(db, monkeypatch):
    configure_brevo(monkeypatch)
    monkeypatch.setattr(config, "BREVO_API_KEY", "")
    monkeypatch.setattr(config, "BREVO_SENDER_EMAIL", "")

    def unexpected_request(*_args, **_kwargs):
        pytest.fail(f"unexpected email request: {_args}, {_kwargs}")

    monkeypatch.setattr(notifications.httpx, "post", unexpected_request)
    result = notifications.send_announcement_notification(
        db, Announcement(title="Campus update", category="News", body="Read this update."))

    assert result == notifications.NotificationResult("not_configured", 0)


def test_record_status_email_is_sent_by_brevo_to_record_owner(monkeypatch):
    configure_brevo(monkeypatch)
    requests = []

    def fake_post(url, **kwargs):
        requests.append((url, kwargs))
        return Response(payload={"messageId": "sent"})

    monkeypatch.setattr(notifications.httpx, "post", fake_post)
    result = notifications.send_record_status_notification(
        "sam@nemsu.edu.ph", "reports", 42, "Under Review")

    assert result == notifications.NotificationResult("sent", 1)
    url, request = requests[0]
    assert url == notifications.BREVO_SEND_URL
    payload = request["json"]
    assert payload["sender"] == {"name": "NEMSAI", "email": "notifications@example.com"}
    assert payload["to"] == [{"email": "sam@nemsu.edu.ph"}]
    assert "Under Review" in payload["subject"]
    assert "http://localhost:8000/reports" in payload["textContent"]


def test_brevo_rate_limit_falls_back_to_gmail_for_record_owner(monkeypatch):
    configure_brevo(monkeypatch, gmail_fallback=True)
    requests = []

    def fake_post(url, **kwargs):
        requests.append((url, kwargs))
        if url == notifications.BREVO_SEND_URL:
            return Response(429, {"code": "rate_limit_exceeded"})
        if url == notifications.TOKEN_URL:
            return Response(200, {"access_token": "access-token"})
        return Response(200, {"id": "sent"})

    monkeypatch.setattr(notifications.httpx, "post", fake_post)
    result = notifications.send_record_status_notification(
        "sam@nemsu.edu.ph", "reports", 42, "Under Review")

    assert result == notifications.NotificationResult("sent", 1)
    assert [url for url, _ in requests] == [
        notifications.BREVO_SEND_URL, notifications.TOKEN_URL, notifications.SEND_URL]
    gmail_request = requests[-1][1]
    message = BytesParser(policy=policy.default).parsebytes(
        base64.urlsafe_b64decode(gmail_request["json"]["raw"] + "==="))
    assert message["To"] == "sam@nemsu.edu.ph"


def test_brevo_quota_falls_back_privately_and_tracks_partial_announcement_delivery(db, monkeypatch):
    configure_brevo(monkeypatch, gmail_fallback=True)
    db.add_all([
        User(google_id=f"brevo-quota-user-{index}", name=f"User {index}",
             email=f"quota{index}@nemsu.edu.ph", role="student")
        for index in range(51)
    ])
    announcement = Announcement(title="Campus update", category="News", body="Read this update.")
    db.add(announcement)
    db.commit()
    gmail_sends = 0
    requests = []

    def fake_post(url, **kwargs):
        nonlocal gmail_sends
        requests.append((url, kwargs))
        if url == notifications.BREVO_SEND_URL:
            return Response(400, {"code": "not_enough_credits", "message": "Insufficient credits"})
        if url == notifications.TOKEN_URL:
            return Response(200, {"access_token": "access-token"})
        gmail_sends += 1
        return Response(200, {"id": "sent"}) if gmail_sends == 1 else Response(403)

    monkeypatch.setattr(notifications.httpx, "post", fake_post)
    with pytest.raises(notifications.GmailNotificationError) as raised:
        notifications.send_announcement_notification(db, announcement)

    assert raised.value.delivered_count == 50
    assert raised.value.recipient_count == 51
    first_gmail_request = next(
        kwargs for url, kwargs in requests if url == notifications.SEND_URL)
    message = BytesParser(policy=policy.default).parsebytes(
        base64.urlsafe_b64decode(first_gmail_request["json"]["raw"] + "==="))
    assert str(message["To"]) == "undisclosed-recipients:;"
    assert len(getaddresses([str(message["Bcc"])])) == 50


def test_brevo_non_quota_failure_does_not_fall_back(monkeypatch):
    configure_brevo(monkeypatch, gmail_fallback=True)
    requests = []

    def fake_post(url, **kwargs):
        requests.append(url)
        return Response(401, {"code": "unauthorized"})

    monkeypatch.setattr(notifications.httpx, "post", fake_post)
    with pytest.raises(notifications.GmailNotificationError, match="HTTP 401"):
        notifications.send_record_status_notification(
            "sam@nemsu.edu.ph", "reports", 42, "Under Review")

    assert requests == [notifications.BREVO_SEND_URL]


def test_quota_fallback_requires_complete_gmail_configuration(monkeypatch):
    configure_brevo(monkeypatch)
    monkeypatch.setattr(config, "GMAIL_CLIENT_ID", "client-id")
    monkeypatch.setattr(config, "GMAIL_CLIENT_SECRET", "")
    monkeypatch.setattr(config, "GMAIL_REFRESH_TOKEN", "")

    def fake_post(url, **_kwargs):
        assert url == notifications.BREVO_SEND_URL
        return Response(429, {"code": "rate_limit_exceeded"})

    monkeypatch.setattr(notifications.httpx, "post", fake_post)
    with pytest.raises(notifications.GmailNotificationError, match="GMAIL_CLIENT_SECRET"):
        notifications.send_record_status_notification(
            "sam@nemsu.edu.ph", "reports", 42, "Under Review")
