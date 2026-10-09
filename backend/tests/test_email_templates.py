"""Presentation contracts for every mail type, with synthetic data only."""

import json
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser

import pytest
from common.email_templates import (
    SUBSCRIPTION_TITLES,
    render_account_email,
    render_subscription_email,
)

PURPOSES = ("PARENT_ACCOUNT_ACTIVATION", "RECOVERY_EMAIL_VERIFICATION", "PASSWORD_RESET")
EXPIRY = datetime(2026, 10, 8, 12, 30, tzinfo=UTC)
LINK = "https://portal.example.invalid/reset-password#token=" + "a" * 128
SNAPSHOT = {
    "school_name": "مدرسة <الأفق> & المعرفة",
    "plan_name": "الباقة السنوية",
    "status_label": "نشط",
    "starts_at": "2026-10-08 09:00",
    "ends_at": "2027-10-08 09:00",
    "grace_ends_at": "2027-10-15 09:00",
    "duration": "12 شهر",
    "price": "500.00 SAR",
    "contract_version": "internal-contract-do-not-display",
}


class Document(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.tags = []
        self.links = []
        self.data = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == "a":
            self.links.append(dict(attrs)["href"])

    def handle_data(self, data):
        self.data.append(data)


def assert_layout(html):
    document = Document(html)
    assert ("html", {"lang": "ar", "dir": "rtl"}) in document.tags
    assert sum(tag == "h1" for tag, _ in document.tags) == 1
    assert all(tag not in {"script", "iframe", "img", "form", "link"}
               for tag, _ in document.tags)
    assert not any(key.startswith("on") for _, attrs in document.tags for key in attrs)
    assert "url(" not in html and "@import" not in html
    assert "#11786d" in html and "#183c37" in html and "#a56a22" in html
    assert any(tag == "table" and attrs.get("role") == "presentation"
               for tag, attrs in document.tags)
    assert "منصة المواظبة" in html and "إدارة مدرسية أكثر وضوحًا" in html
    return document


@pytest.mark.parametrize("purpose", PURPOSES)
def test_account_templates_keep_action_expiry_security_and_plaintext(purpose):
    subject, text, html = render_account_email(
        purpose=purpose, link=LINK, expires_at=EXPIRY, school_name=SNAPSHOT["school_name"],
    )
    document = assert_layout(html)
    assert document.links == [LINK, LINK]
    assert LINK in text
    assert "2026-10-08، الساعة 15:30 (بتوقيت الرياض)" in text
    assert "2026-10-08، الساعة 15:30 (بتوقيت الرياض)" in html
    assert "لن تتغير بيانات حسابك بمجرد فتح الرابط" in text
    assert "لا تشاركه" in text and "إذا لم تطلب" in text
    preheader = next(data for data in document.data if "أكمل الإجراء من خلال" in data)
    assert "#token=" not in preheader and "a" * 128 not in subject
    if purpose == "PARENT_ACCOUNT_ACTIVATION":
        assert SNAPSHOT["school_name"] in text and SNAPSHOT["school_name"] in subject
        assert "مدرسة &lt;الأفق&gt; &amp; المعرفة" in html
        assert "حسابك الحالي" in text
    else:
        assert SNAPSHOT["school_name"] not in text + subject + html


@pytest.mark.parametrize("kind", SUBSCRIPTION_TITLES)
def test_subscription_templates_preserve_only_whitelisted_details(kind):
    subject, text, html = render_subscription_email(
        kind, SNAPSHOT, portal_origin="https://portal.example.invalid",
    )
    document = assert_layout(html)
    assert subject == SUBSCRIPTION_TITLES[kind] + " — منصة المواظبة"
    for key, value in SNAPSHOT.items():
        if key != "contract_version":
            assert value in text and value in unescape(html)
    assert SNAPSHOT["contract_version"] not in html + text
    assert "سعر الباقة" in text and "فاتورة" not in text
    assert "بتوقيت الرياض" in text and "اختيار المدرسة" in text
    assert document.links == ["https://portal.example.invalid/subscription"] * 2
    assert "#token=" not in html + text


@pytest.mark.parametrize("origin", ["", "javascript:alert(1)", "http://example.invalid",
                                     "https://user:secret@example.invalid", "https://example.invalid/path",
                                     "https://example.invalid?q=1", "https://example.invalid/#x",
                                     "https://example.invalid:bad", "https://example.invalid\n"])
def test_bad_optional_subscription_origin_omits_link_but_preserves_message(origin):
    _, text, html = render_subscription_email("DETAILS", SNAPSHOT, portal_origin=origin)
    assert Document(html).links == []
    assert SNAPSHOT["school_name"] in text and "صفحة الاشتراك" in text


def test_missing_subscription_values_do_not_invent_billing_or_dates():
    _, text, html = render_subscription_email("EXPIRED", {"school_name": "مدرسة الأفق"})
    assert "سعر الباقة:" not in text and "نهاية مهلة السماح:" not in text
    assert "بتوقيت الرياض" not in text
    assert "500" not in html


def test_hostile_content_cannot_add_markup_or_an_action_link():
    hostile = '<img src="https://evil.invalid/x" onerror="alert(1)"> & <script>bad</script>'
    _, _, html = render_subscription_email("DETAILS", {"school_name": hostile})
    assert_layout(html)
    assert hostile in unescape(html)
    assert not Document(html).links


@pytest.mark.parametrize("purpose", PURPOSES)
def test_account_payload_fits_existing_transport_limit_with_long_school_and_token(purpose):
    subject, text, html = render_account_email(
        purpose=purpose, link=LINK, expires_at=EXPIRY, school_name="م" * 255,
    )
    body = json.dumps({"from": "School <mail@example.invalid>", "to": ["x@example.invalid"],
                       "subject": subject, "text": text, "html": html},
                      ensure_ascii=False).encode()
    assert len(body) < 16 * 1024


@pytest.mark.parametrize("kind", SUBSCRIPTION_TITLES)
def test_subscription_payload_fits_existing_limit_with_long_names(kind):
    subject, text, html = render_subscription_email(
        kind, {**SNAPSHOT, "school_name": "م" * 255, "plan_name": "ب" * 255},
        portal_origin="https://portal.example.invalid",
    )
    body = json.dumps({"from": "Subscription <mail@example.invalid>", "to": ["x@example.invalid"],
                       "subject": subject, "text": text, "html": html},
                      ensure_ascii=False).encode()
    assert len(body) < 16 * 1024


def test_unsupported_kinds_and_naive_expiry_are_rejected():
    with pytest.raises(ValueError):
        render_account_email(purpose="MARKETING", link=LINK, expires_at=EXPIRY)
    with pytest.raises(ValueError):
        render_account_email(purpose="PASSWORD_RESET", link=LINK,
                             expires_at=EXPIRY.replace(tzinfo=None))
    with pytest.raises(KeyError):
        render_subscription_email("PAYMENT_RECEIPT", SNAPSHOT)
