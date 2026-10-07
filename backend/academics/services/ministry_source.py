"""Read the public HTML data used by the Ministry's academic-calendar page.

The Ministry has not documented these pages as an integration API. Reject
redirects, malformed dates and conflicting events; retain each original title.
"""

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

SOURCE_PAGE = "https://www.moe.gov.sa/ar/education/generaleducation/Pages/academicCalendar.aspx"
SOURCE_ROOT = "https://www.moe.gov.sa/ar/education/generaleducation/DataSources/"
SEMESTER_POLICY_SOURCE = "https://sites.moe.gov.sa/Riyadh/news/news-165/"
# User-specified operational rule. This is not a date published by the Ministry.
DERIVATION_RULE = "MIDYEAR_PLUS_9_DAYS_V1"
PARSER_VERSION = 3
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
REQUIRED_DATES = (
    "year_start",
    "year_end",
    "semester_1_start",
    "semester_1_end",
    "semester_2_start",
    "semester_2_end",
)


class MinistrySourceError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise MinistrySourceError("MINISTRY_REDIRECT_REJECTED")


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "site":
            row = dict(attrs)
            if len(row) != len(attrs):
                raise MinistrySourceError("MINISTRY_INVALID_DOCUMENT")
            self.rows.append(row)


def read_document(url):
    # Only fixed paths constructed below. Never accept a URL from a school/user.
    if not url.startswith(SOURCE_ROOT):
        raise MinistrySourceError("MINISTRY_URL_REJECTED")
    try:
        request = Request(  # noqa: S310 - fixed HTTPS Ministry prefix checked above
            url, headers={"User-Agent": "Xmansx-Calendar/1.0"}
        )
        with build_opener(_NoRedirect()).open(request, timeout=15) as response:
            if response.status != 200 or response.headers.get_content_type() != "text/html":
                raise MinistrySourceError("MINISTRY_INVALID_DOCUMENT")
            body = response.read(MAX_DOCUMENT_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise MinistrySourceError("MINISTRY_UNAVAILABLE") from exc
    if len(body) > MAX_DOCUMENT_BYTES:
        raise MinistrySourceError("MINISTRY_DOCUMENT_TOO_LARGE")
    try:
        parser = _Rows()
        parser.feed(body.decode("utf-8-sig"))
        parser.close()
    except (UnicodeError, ValueError) as exc:
        raise MinistrySourceError("MINISTRY_INVALID_DOCUMENT") from exc
    if not parser.rows:
        raise MinistrySourceError("MINISTRY_EMPTY_DOCUMENT")
    return {"url": url, "sha256": hashlib.sha256(body).hexdigest(), "rows": parser.rows}


def _normal(text):
    text = unicodedata.normalize("NFKC", text).replace("ـ", "")
    text = re.sub(r"[\u064b-\u065f\u0670]", "", text)
    return " ".join(text.translate(str.maketrans("أإآى", "اااي")).split())


def _kind(title):
    title = _normal(title)
    if "بداية" in title and (
        "بداية العام الدراسي" in title or "بداية الدراسة للعام الدراسي" in title
    ):
        return "year_start"
    if "نهاية العام الدراسي" in title and "نهاية دوام" in title:
        return "year_end"
    if title in ("اجازة منتصف العام الدراسي", "بداية اجازة منتصف العام الدراسي"):
        return "midyear_break_start"
    for sequence, word in ((1, "الاول"), (2, "الثاني"), (3, "الثالث")):
        if not re.search(rf"(?:ال|لل)فصل الدراسي {word}", title):
            continue
        if (
            "بداية الدراسة" in title or title.startswith(f"بداية الفصل الدراسي {word}")
        ) and "بعد" not in title:
            return f"semester_{sequence}_start"
        if title.startswith(f"نهاية الفصل الدراسي {word}"):
            return f"semester_{sequence}_end"
    return None


def normalize_documents(documents):
    events = {}
    for document in documents[1:]:
        for row in document["rows"]:
            try:
                event_id, title, raw_date = row["id"], row["title"], row["dategregorian"]
                if not re.fullmatch(r"\d+", event_id) or not title.strip():
                    raise ValueError
                if not re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", raw_date):
                    raise ValueError
                event_date = datetime.strptime(raw_date, "%d/%m/%Y").date().isoformat()
            except (KeyError, ValueError) as exc:
                raise MinistrySourceError("MINISTRY_INVALID_EVENT") from exc
            event = {
                "id": event_id,
                "title": title,
                "date": event_date,
                "basis": "PUBLISHED",
                "hijri_date": row.get("eventdate", ""),
                "url": document["url"],
            }
            if event_id in events and events[event_id] != event:
                raise MinistrySourceError("MINISTRY_CONFLICTING_EVENT")
            events[event_id] = event
    starts = sorted({e["date"] for e in events.values() if _kind(e["title"]) == "year_start"})
    calendars = []
    for index, start in enumerate(starts):
        next_start = starts[index + 1] if index + 1 < len(starts) else "9999-12-31"
        selected = [e for e in events.values() if start <= e["date"] < next_start]
        evidence = {}
        problems = []
        for event in selected:
            key = _kind(event["title"])
            if key is None:
                continue
            if key in evidence and evidence[key]["date"] != event["date"]:
                problems.append(f"CONFLICT:{key}")
            evidence[key] = event
        # Explicit Ministry semester dates take precedence over any operational rule.
        # Two semesters apply to the current four-year framework (2025–2028 openings).
        two_semesters = 2025 <= int(start[:4]) <= 2028
        if any(key.startswith("semester_3_") for key in evidence):
            problems.append("UNSUPPORTED_SEMESTER_SYSTEM")
        # An annual student opening is sufficient evidence for the first opening;
        # never use teacher return dates, holiday starts or Gregorian-year shifts.
        if "semester_1_start" not in evidence:
            evidence["semester_1_start"] = {**evidence["year_start"], "basis": "YEAR_BOUNDARY"}
        if two_semesters and not any(key.startswith("semester_3_") for key in evidence):
            midyear = evidence.get("midyear_break_start")
            if midyear:
                for key, offset, rule in (
                    ("semester_1_end", -1, "DAY_BEFORE_MIDYEAR_BREAK"),
                    ("semester_2_start", 9, DERIVATION_RULE),
                ):
                    if key not in evidence:
                        calculated = date.fromisoformat(midyear["date"]) + timedelta(days=offset)
                        evidence[key] = {
                            **midyear,
                            "date": calculated.isoformat(),
                            "source_date": midyear["date"],
                            "basis": "CALCULATED",
                            "rule": rule,
                            "offset_days": offset,
                        }
                        if key == "semester_2_start" and calculated.weekday() != 6:
                            problems.append("CALCULATED_RETURN_NOT_SUNDAY")
            if "semester_2_end" not in evidence and "year_end" in evidence:
                evidence["semester_2_end"] = {
                    **evidence["year_end"],
                    "basis": "YEAR_BOUNDARY",
                    "policy_url": SEMESTER_POLICY_SOURCE,
                }
        elif not two_semesters:
            problems.append("SEMESTER_POLICY_NOT_VERIFIED")
        dates = {key: evidence[key]["date"] if key in evidence else None for key in REQUIRED_DATES}
        missing = [key for key in REQUIRED_DATES if dates[key] is None]
        if dates["year_end"]:
            duration = (
                datetime.fromisoformat(dates["year_end"]) - datetime.fromisoformat(start)
            ).days
            if not 180 <= duration <= 370:
                problems.append("INVALID_YEAR_RANGE")
        if not missing:
            ys, ye, s1, e1, s2, e2 = (dates[key] for key in REQUIRED_DATES)
            if not ys <= s1 <= e1 < s2 <= e2 <= ye:
                problems.append("INVALID_SEMESTER_ORDER")
        calendars.append(
            {
                "name": f"{start[:4]}/{int(start[:4]) + 1}",
                "dates": dates,
                "evidence": evidence,
                "missing": missing,
                "problems": sorted(set(problems)),
                "events": selected,
                "status": "INVALID" if problems else "INCOMPLETE" if missing else "READY",
            }
        )
    if not calendars:
        raise MinistrySourceError("MINISTRY_NO_ACADEMIC_YEAR")
    return calendars


def fetch_ministry_calendar():
    years_document = read_document(SOURCE_ROOT + "Years.aspx")
    years = []
    for row in years_document["rows"]:
        title = row.get("title", "")
        if not re.fullmatch(r"[0-9]{4}", title) or not 1400 <= int(title) <= 1600:
            raise MinistrySourceError("MINISTRY_INVALID_YEAR_INDEX")
        years.append(int(title))
    # Read adjacent Hijri lists: a Gregorian school year spans two such lists.
    documents = [years_document] + [
        read_document(SOURCE_ROOT + f"AcademicCalendar.aspx?Year={year}")
        for year in sorted(set(years))[-4:]
    ]
    calendars = normalize_documents(documents)
    # ASP.NET emits changing page state even when the public events are identical.
    # Retain the raw hashes as evidence, but deduplicate by the source rows and rules.
    semantic_documents = [
        {
            "url": document["url"],
            "rows": sorted(
                document["rows"],
                key=lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True),
            ),
        }
        for document in documents
    ]
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "documents": semantic_documents,
                "rule": DERIVATION_RULE,
                "parser_version": PARSER_VERSION,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return fingerprint, documents, calendars
