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


def _render_report(report: Optional[dict]) -> str:
    """HTML block summarizing the AI reviewer report (author-facing)."""
    if not report:
        return ""
    assert isinstance(report, dict)
    scores = report.get("scores") if isinstance(report.get("scores"), dict) else {}
    rationale = report.get("rationale") if isinstance(report.get("rationale"), dict) else {}
    ii = report.get("impact_index") if isinstance(report.get("impact_index"), dict) else {}
    red_flags = report.get("red_flags") if isinstance(report.get("red_flags"), list) else []
    one_line = str(report.get("one_line") or "")
    model = str(report.get("model") or "")

    rows = []
    labels = [
        ("originality", "Originality"),
        ("methodological_rigor", "Methodological rigor"),
        ("clarity", "Clarity"),
        ("relevance", "Relevance"),
        ("bibliography", "Bibliography"),
    ]
    for key, label in labels:
        sc = scores.get(key)
        rat = str(rationale.get(key) or "")
        cell = f'<strong>{sc if sc is not None else "—"}</strong>/10'
        if rat:
            cell += f'<br><span style="color:#5a7266;font-size:13px">{_html.escape(rat)}</span>'
        rows.append(
            f'<tr><td style="padding:6px 8px;border-bottom:1px solid #e8efe9;'
            f'color:#2d6a4f;font-weight:600">{label}</td>'
            f'<td style="padding:6px 8px;border-bottom:1px solid #e8efe9">{cell}</td></tr>')

    ii_score = ii.get("score")
    conf = ii.get("confidence")
    impact_html = (f"<strong>{ii_score}</strong>/10" if ii_score is not None else "—")
    if conf is not None:
        impact_html += f' <span style="color:#5a7266;font-size:13px">(confidence {conf})</span>'

    flags_html = ""
    if red_flags:
        items = "".join(
            f"<li style=\"margin:4px 0\">{_html.escape(str(f))}</li>" for f in red_flags
        )
        flags_html = (
            '<div style="margin-top:14px;background:#fdf3ef;border:1px solid #f2d4c5;'
            'border-radius:8px;padding:12px 14px">'
            '<div style="font-weight:600;color:#9a3b1e;font-size:14px;margin-bottom:6px">'
            'Flags identified by the reviewer</div>'
            f'<ul style="margin:0;padding-left:18px;font-size:13px;color:#6b4a3a;line-height:1.5">{items}</ul>'
            '</div>')

    model_note = f" · model: {_html.escape(model)}" if model else ""
    return (
        '<div style="margin-top:20px;border-top:1px solid #d8e6d7;padding-top:16px">'
        '<div style="font-size:13px;letter-spacing:1.5px;color:#5a7266;margin-bottom:8px">'
        'AI REVIEWER REPORT</div>'
        f'<p style="font-size:15px;line-height:1.6;margin:0 0 12px;font-style:italic">'
        f'“{_html.escape(one_line)}”</p>'
        '<table style="font-size:14px;border-collapse:collapse;width:100%">'
        + "".join(rows) +
        f'<tr><td style="padding:6px 8px;border-bottom:1px solid #e8efe9;color:#2d6a4f;'
        f'font-weight:600">Impact index</td>'
        f'<td style="padding:6px 8px;border-bottom:1px solid #e8efe9">{impact_html}</td></tr>'
        '</table>'
        f'<p style="font-size:12px;color:#8aa898;margin:10px 0 0">{flags_html and "The review may be improved by addressing: " or ""}'
        f'This AI report is advisory — the publication decision was made by a human moderator.{model_note}</p>'
        + flags_html +
        '</div>')


def _render(kind: str, data: dict, report: Optional[dict] = None) -> str:
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
                            reviewer=reviewer, link=link) + _render_report(report)


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


def notify_auth_decision(kind: str, submission: dict, rid: str = "",
                         report: Optional[dict] = None) -> bool:
    """Send an accepted/rejected notification for a submission.

    `submission` is the payload dict (must include submitted_by with the
    author's contact email, contact_email, title, area — with reviewer name).
    `report` (optional) is the AI screening score dict; when provided the
    email includes the author-facing 'AI reviewer report' block explaining
    the impact index. Returns True if sent (or author email missing), False.
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
    }, report=report)
    return _send(email, subject, body, cc=EDITOR_CC or None)