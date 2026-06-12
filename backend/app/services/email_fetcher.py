"""
JobRadar — Gmail job-alert scanner (Feature 1, on-demand add-on).

Reads job-alert emails from Gmail over IMAP (app password), restricted to an
editable sender allowlist + a recent window, extracts postings via Groq, and
returns normalized job dicts for the standard pipeline.

This is NOT a refresh fetcher layer — it's triggered on demand so its Groq
usage (extraction) never collides with the refresh's per-minute TPM window.
Secrets (GMAIL_ADDRESS, GMAIL_APP_PASSWORD) come from env only; the sender
allowlist + scan window are stored in the DB and editable from the UI.
"""
import os
import re
import json
import time
import email
import imaplib
import logging
from email.header import decode_header
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from bs4 import BeautifulSoup

from app.database import list_email_senders, is_email_seen, get_setting
from app.services.ai_agent import _call_groq, _clean_groq_json, is_ai_enabled, FAST_MODEL

logger = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
MAX_EMAILS_PER_SCAN = 20      # cap messages processed per scan
GAP_BETWEEN_EMAILS = 1.5      # seconds between Groq extraction calls (TPM courtesy)

# Query params to drop when canonicalizing tracking-wrapped alert links
_TRACKING_PARAMS = {
    "trk", "trackingid", "refid", "rcm", "lipi", "midtoken", "midsig",
    "eid", "otptoken", "lgcta", "src", "source", "ref", "campaign",
}


def is_email_enabled():
    """True only when both Gmail creds are present in env."""
    return bool(os.environ.get("GMAIL_ADDRESS") and os.environ.get("GMAIL_APP_PASSWORD"))


def test_connection():
    """Attempt an IMAP login (no fetch). Returns (ok: bool, error: str|None)."""
    if not is_email_enabled():
        return False, "GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set in environment"
    try:
        M = _connect()
        try:
            M.logout()
        except Exception:
            pass
        return True, None
    except Exception as e:
        return False, str(e)


def _connect():
    addr = os.environ.get("GMAIL_ADDRESS", "")
    pwd = os.environ.get("GMAIL_APP_PASSWORD", "")
    M = imaplib.IMAP4_SSL(IMAP_HOST)
    M.login(addr, pwd)
    return M


def _select_mailbox(M):
    """Open the configured Gmail label if set, else INBOX (read-only)."""
    label = os.environ.get("GMAIL_LABEL", "").strip()
    if label:
        typ, _ = M.select(f'"{label}"', readonly=True)
        if typ == "OK":
            return
        logger.warning(f"[email] label '{label}' not found, falling back to INBOX")
    M.select("INBOX", readonly=True)


def _decode_header(value):
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(enc or "utf-8", errors="ignore"))
            except Exception:
                out.append(text.decode("utf-8", errors="ignore"))
        else:
            out.append(text)
    return "".join(out)


def _strip_html(html):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["style", "script"]):
        t.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def _extract_body(msg):
    """Return readable text from an email message (prefers HTML, then plain)."""
    html_body, text_body = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            try:
                payload = part.get_payload(decode=True)
            except Exception:
                continue
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="ignore")
            except Exception:
                decoded = payload.decode("utf-8", errors="ignore")
            if ctype == "text/html" and not html_body:
                html_body = decoded
            elif ctype == "text/plain" and not text_body:
                text_body = decoded
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="ignore")
            if msg.get_content_type() == "text/html":
                html_body = decoded
            else:
                text_body = decoded

    if html_body:
        return _strip_html(html_body)
    return re.sub(r"\s+", " ", text_body).strip()


def _canonicalize_url(url):
    """Strip tracking query params so email jobs dedupe against scraped ones."""
    try:
        parts = urlsplit(url)
        kept = [
            (k, v) for k, v in parse_qsl(parts.query)
            if not (k.lower().startswith("utm_") or k.lower() in _TRACKING_PARAMS)
        ]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))
    except Exception:
        return url


def _domain_of(url):
    try:
        host = urlsplit(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


_EXTRACT_SYSTEM = """You extract job postings from a job-alert email.
Return ONLY a valid JSON array — never markdown, never prose.
Each element: {"title": str, "company": str, "location": str, "url": str}.
- "url" must be the direct link to the job/application.
- If the email lists multiple jobs, return all of them.
- If there are no real job postings, return [].
Do not invent jobs. Keep titles/companies as written."""


def _extract_jobs_from_email(subject, text):
    """One Groq call per email → list of {title, company, location, url}."""
    prompt = f"Subject: {subject}\n\nEmail body:\n{text}"
    result = _call_groq(prompt, _EXTRACT_SYSTEM, model=FAST_MODEL, max_tokens=1500, temperature=0.1)
    if not result:
        return []
    try:
        cleaned = _clean_groq_json(result)
        data = json.loads(cleaned)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.debug(f"[email] extraction parse failed: {e}")
        return []


def fetch_email_jobs():
    """Scan allowlisted job-alert mail and return (jobs, processed_message_ids).

    jobs are normalized dicts ready for _store_jobs; processed_message_ids should
    be marked seen by the caller so re-scans skip them.
    """
    if not is_email_enabled():
        logger.info("[email] disabled — GMAIL_APP_PASSWORD not set")
        return [], []
    if not is_ai_enabled():
        logger.info("[email] Groq not enabled — cannot extract; skipping")
        return [], []

    senders = [s["value"] for s in list_email_senders(enabled_only=True)]
    if not senders:
        logger.info("[email] no enabled senders in allowlist")
        return [], []

    try:
        scan_days = int(get_setting("email_scan_days", 7))
    except (TypeError, ValueError):
        scan_days = 7

    raw_query = f'from:({" OR ".join(senders)}) newer_than:{scan_days}d'
    logger.info(f"[email] scanning: {raw_query}")

    M = _connect()
    jobs, processed_mids, seen_urls = [], [], set()
    try:
        _select_mailbox(M)
        typ, data = M.search(None, "X-GM-RAW", f'"{raw_query}"')
        if typ != "OK" or not data or not data[0]:
            logger.info("[email] no matching messages")
            return [], []

        ids = data[0].split()[-MAX_EMAILS_PER_SCAN:]  # most recent N
        logger.info(f"[email] {len(ids)} candidate messages")

        for idx, num in enumerate(ids):
            try:
                typ, msgdata = M.fetch(num, "(RFC822)")
                if typ != "OK" or not msgdata or not msgdata[0]:
                    continue
                msg = email.message_from_bytes(msgdata[0][1])
                mid = (msg.get("Message-ID") or "").strip()
                if mid and is_email_seen(mid):
                    continue
                subject = _decode_header(msg.get("Subject", ""))
                body = _extract_body(msg)
                if not body:
                    if mid:
                        processed_mids.append(mid)
                    continue

                extracted = _extract_jobs_from_email(subject, body[:4000])
                for j in extracted:
                    url = (j.get("url") or "").strip()
                    title = (j.get("title") or "").strip()
                    if not url or not title:
                        continue
                    canon = _canonicalize_url(url)
                    if canon in seen_urls:
                        continue
                    seen_urls.add(canon)
                    jobs.append({
                        "title": title[:150],
                        "company": (j.get("company") or "Unknown")[:100],
                        "location": (j.get("location") or "")[:100],
                        "source_url": canon,
                        "source_domain": _domain_of(canon) or "email",
                        "description_snippet": (f"From email alert: {subject}")[:300],
                        "posted_date": "",
                        "skills_found": json.dumps([]),
                    })

                if mid:
                    processed_mids.append(mid)

                if idx < len(ids) - 1:
                    time.sleep(GAP_BETWEEN_EMAILS)  # spacing for Groq TPM
            except Exception as e:
                logger.debug(f"[email] message error: {e}")
                continue

        logger.info(f"[email] extracted {len(jobs)} jobs from {len(processed_mids)} emails")
        return jobs, processed_mids
    finally:
        try:
            M.logout()
        except Exception:
            pass
