"""Render all mail designs locally with synthetic data, without sending mail."""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from common.email_templates import (  # noqa: E402
    SUBSCRIPTION_TITLES,
    render_account_email,
    render_subscription_email,
)


def samples():
    expiry = datetime(2026, 10, 9, 12, 30, tzinfo=UTC)
    routes = {
        "PARENT_ACCOUNT_ACTIVATION": "/parent/activate",
        "RECOVERY_EMAIL_VERIFICATION": "/parent/verify-email",
        "PASSWORD_RESET": "/reset-password",
    }
    for kind, route in routes.items():
        yield kind, render_account_email(
            purpose=kind,
            link=f"https://portal.example.invalid{route}#token=" + "preview-only-" * 4,
            expires_at=expiry, school_name="مدرسة الأفق النموذجية",
        )
    for kind in SUBSCRIPTION_TITLES:
        ends = datetime(2027, 10, 8, 9, tzinfo=ZoneInfo("Asia/Riyadh"))
        status = "نشط"
        grace = ""
        if kind in {"REMINDER_7", "REMINDER_1"}:
            ends = datetime(2026, 10, 15 if kind == "REMINDER_7" else 9, 9,
                            tzinfo=ZoneInfo("Asia/Riyadh"))
        elif kind in {"GRACE_STARTED", "EXPIRED", "SUSPENDED", "CANCELLED"}:
            ends = datetime(2026, 10, 7, 9, tzinfo=ZoneInfo("Asia/Riyadh"))
            status = {"GRACE_STARTED": "مهلة السماح", "EXPIRED": "منتهٍ",
                      "SUSPENDED": "موقوف", "CANCELLED": "ملغى"}[kind]
            if kind == "GRACE_STARTED":
                grace = "2026-10-14 09:00"
        snapshot = {
            "school_name": "مدرسة الأفق النموذجية", "plan_name": "الباقة السنوية",
            "status_label": status,
            "starts_at": (ends - timedelta(days=365)).strftime("%Y-%m-%d %H:%M"),
            "ends_at": ends.strftime("%Y-%m-%d %H:%M"), "grace_ends_at": grace,
            "duration": "12 شهرًا", "price": "500.00 SAR",
        }
        yield kind, render_subscription_email(kind, snapshot,
                                             portal_origin="https://portal.example.invalid")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)
    entries, cards = [], []
    for kind, (subject, text, html) in samples():
        filename = kind.lower()
        (output / f"{filename}.html").write_text(html, encoding="utf-8")
        (output / f"{filename}.txt").write_text(text, encoding="utf-8")
        entries.append({"kind": kind, "subject": subject, "file": f"{filename}.html",
                        "html_bytes": len(html.encode()), "text_bytes": len(text.encode())})
        cards.append(
            f'<article id="{filename}"><h2>{escape(subject)}</h2>'
            f'<p><a href="{filename}.html">فتح الرسالة</a> · '
            f'<a href="{filename}.txt">النسخة النصية</a></p>'
            f'<iframe title="{escape(subject, quote=True)}" src="{filename}.html" '
            'loading="lazy"></iframe></article>'
        )
    gallery = (
        '<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>معاينة بريد منصة المواظبة</title><style>'
        'body{margin:0;padding:24px;background:#f4f8f6;color:#16332e;font:16px/1.8 Tahoma,Arial}'
        'h1{margin:0}header{max-width:1200px;margin:0 auto 32px}a{color:#11786d}'
        'main{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;max-width:1300px;margin:auto}'
        'article{background:#fffefd;border:1px solid #dce8e3;border-radius:12px;'
        'padding:16px;min-width:0}'
        'h2{font-size:18px}iframe{border:0;width:100%;height:1180px;background:#f4f8f6}'
        '@media(max-width:800px){body{padding:12px}main{grid-template-columns:1fr}}'
        '</style><header><h1>بريد منصة المواظبة</h1>'
        '<p>معاينة محلية للأنواع العشرة · بيانات صناعية · الروابط لا تنفذ إجراءات فعلية</p>'
        '<p>ألوان المنصة، تخطيط عربي، ونسخة نصية لكل رسالة.</p></header><main>'
        + "".join(cards) + "</main></html>"
    )
    (output / "index.html").write_text(gallery, encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps(entries, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(f"Rendered {len(entries)} templates; no mail sent. Gallery: {output / 'index.html'}")


if __name__ == "__main__":
    main()
