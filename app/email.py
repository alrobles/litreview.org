"""Email notifications for LitReview — Resend API (transaccional, gratuito).

Sends accept/reject notifications to the submitting author when a preprint is
moderated. Non-blocking by design: the moderation (approve/reject) completes
even if the email fails; failures are logged.

Env:
  RESEND_API_KEY      — API key (host file ~/env/litreview-email-key)
  LITREVIEW_EMAIL_FROM— verified sender, e.g. "LitReview <preprints@litreview.org>"
  LITREVIEW_EDITOR_CC — editorial copy-to address (optional)
  LITREVIEW_BASE_URL  — for links in the email
"""
from __future__ import annotations

import html as _html
import json
import os
import urllib.request
from typing import Optional

RESEND_URL = "https://api.resend.com/emails"
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM = os.environ.get("LITREVIEW_EMAIL_FROM", "LitReview <onboarding@resend.dev>")
EDITOR_CC = os.environ.get("LITREVIEW_EDITOR_CC", "")
BASE_URL = os.environ.get("LITREVIEW_BASE_URL", "https://litreview.org").rstrip("/")

# plantillas (html simple, inline styles — portables)
_TEMPLATE = """<!doctype html>
<html><body style="margin:0;padding:0;background:#f4f7f5;font-family:Georgia,'Times New Roman',serif;color:#172820">
<div style="max-width:560px;margin:0 auto;padding:32px 20px">
  <div style="background:#fff;border:1px solid #d8e6d7;border-radius:12px;padding:28px">
    <div style="font-size:15px;letter-spacing:2px;color:#2d6a4f;margin-bottom:18px">AI <span style="font-weight:bold">LitReview</span></div>
    <h1 style="font-size:22px;margin:0 0 12px;color:{heading_color}">{heading}</h1>
    <p style="font-size:15px;line-height:1.6;margin:0 0 16px">{body}</p>
    <table style="font-size:14px;border-collapse:collapse;width:100%;margin:14px 0">
      <tr><td style="padding:6px 0;color:#5a7266;width:110px">Preprint</td><td style="padding:6px 0"><strong>{rid}</strong></td></tr>
      <tr><td style="padding:6px 0;color:#5a7266">Title</td><td style="padding:6px 0"><strong>{title}</strong></td></tr>
      <tr><td style="padding:6px 0;color:#5a7266">Area</td><td style="padding:6px 0">{area}</td></tr>
      <tr><td style="padding:6px 0;color:#5a7266">Reviewed by</td><td style="padding:6px 0">{reviewer}</td></tr>
    </table>
    <a href="{link}" style="display:inline-block;background:#2d6a4f;color:#fff;text-decoration:none;padding:10px 18px;border-radius:8px;font-size:14px;font-family:system-ui,sans-serif">View on LitReview</a>
    <p style="font-size:12px;color:#8aa898;margin:22px 0 0;line-height:1.5">LitReview.org · citable literature reviews written by scientists with AI assistance · CC BY 4.0</p>
  </div>
</div></body></html>"""


def _render(kind: str, data: dict) -> str:
    """Render the HTML body for an accept or reject notification."""
    rid = data.get("rid") or "—"
    title = _html.escape(data.get("title") or "")
    area = _html.escape(data.get("area") or "")
    reviewer = _html.escape(data.get("reviewer") or "")
    if kind == "accepted":
        heading = "Your preprint was accepted"
        color = "#2d6a4f"
        body = ("Congratulations — your literature review has been accepted for "
                "publication on LitReview. It is now citable with a permanent "
                "identifier and CC BY 4.0 license, and visible to the community.")
        link = f"{BASE_URL}/abs.html?id={rid}"
    else:
        heading = "Your preprint was not accepted"
        color = "#9a3b1e"
        body = ("Thank you for submitting to LitReview. After review, your "
                "preprint was not accepted for publication. Our editorial "
                "criteria prioritize scientific substance, clear methodology, "
                "and up-to-date references — you are welcome to revise and "
                "resubmit.")
        link = f"{BASE_URL}/submit.html"
    return _TEMPLATE.format(heading=heading, heading_color=color, body=body,
                            rid=_html.escape(rid), title=title, area=area,
                            reviewer=reviewer, link=link)


def _send(to: str, subject: str, body: str, cc: Optional[str] = None) -> bool:
    """POST to Resend. Returns True on success; never raises."""
    if not RESEND_API_KEY:
        print("EMAIL SKIPPED: RESEND_API_KEY not set", flush=True)
        return False
    payload: dict = {"from": FROM, "to": [to], "subject": subject, "html": body}
    if cc:
        payload["cc"] = [cc]
    req = urllib.request.Request(
        RESEND_URL, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {RESEND_API_KEY}",
                 "Content-Type": "application/json",
                 "User-Agent": "LitReview/1.0 (https://litreview.org)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = resp.status == 200
            if not ok:
                print(f"EMAIL FAILED: {resp.status} {resp.read()[:200]}", flush=True)
            return ok
    except Exception as e:
        print(f"EMAIL FAILED: {e}", flush=True)
        return False


def notify_auth_decision(kind: str, submission: dict, rid: str = "") -> bool:
    """Send an accepted/rejected notification for a submission.

    `submission` is the payload dict (must include submitted_by with the
    author's contact email, contact_email, title, area — with reviewer name).
    Returns True if sent (or author email missing), False on failure.
    """
    email = "submitted_by" in submission and submission["submitted_by"].get("email")
    if not email:
        # fallback: contact_email from the submission form
        email = submission.get("contact_email") or submission.get("email")
    if not email:
        print(f"EMAIL SKIPPED: no author email for {submission.get('sid')}", flush=True)
        return False
    subject = ("[LitReview] Your preprint was accepted" if kind == "accepted"
               else "[LitReview] Update on your preprint")
    body = _render(kind, {
        "rid": rid or submission.get("published_id") or "",
        "title": submission.get("title") or "",
        "area": submission.get("area") or "",
        "reviewer": (submission.get("reviewed_by") or {}).get("name", ""),
    })
    return _send(email, subject, body, cc=EDITOR_CC or None)