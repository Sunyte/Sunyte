import requests
from sunyte.config import load_config


def send_alert(message: str):
    cfg = load_config()
    alert_cfg = cfg.get("alerts", {})
    if not alert_cfg.get("enabled"):
        return
    webhook = alert_cfg.get("slack_webhook_url", "")
    if not webhook:
        return
    try:
        requests.post(webhook, json={"text": f":rotating_light: Sunyte: {message}"}, timeout=3)
    except Exception:
        # never let an alert failure break the agent's actual work
        pass
