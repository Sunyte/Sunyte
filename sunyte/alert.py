"""Outbound alerting. Standard-library only (urllib), so the plugin has no
runtime dependencies.

Slack/webhook alerting is a Team-tier feature; escalation (paging a human on a
hard block) is Compliance-tier. On the Free tier every flag is still recorded
locally — it just isn't pushed anywhere.
"""

import json
import urllib.request

from sunyte.config import load_config
from sunyte.tier import at_least


def send_alert(message: str, severity: str = "warn"):
    cfg = load_config()
    alert_cfg = cfg.get("alerts", {}) or {}

    if alert_cfg.get("enabled") and at_least("team"):
        webhook = (alert_cfg.get("slack_webhook_url") or "").strip()
        if webhook:
            _post(webhook, {"text": f":rotating_light: Sunyte: {message}"})

    if severity == "block" and at_least("compliance"):
        _escalate(alert_cfg, message)


def _post(url: str, payload: dict):
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        # never let an alert failure break the agent's actual work
        pass


def _escalate(alert_cfg: dict, message: str):
    """Compliance-tier escalation. The transport (SMTP relay, PagerDuty, an
    email chain) is configured per-org; this records the intent and leaves a
    single seam to wire the real integration into."""
    targets = alert_cfg.get("escalation_emails") or []
    if not targets:
        return
    hook = (alert_cfg.get("escalation_webhook_url") or "").strip()
    if hook:
        _post(hook, {"text": f"[ESCALATION] Sunyte hard block: {message}",
                     "escalate_to": targets})
