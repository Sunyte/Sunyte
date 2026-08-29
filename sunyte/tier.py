"""Tier gating for Sunyte (Free / Team / Compliance).

This is deliberately a thin scaffold: it decides *which tier is active* and
gives the rest of the codebase one place to ask "is this allowed?". The
business model it maps to lives in the README pricing table.

  Free        blocking, kill switch, per-session logging + replay, blocklist editing
  Team        Slack alerts, CSV/Markdown exports, cross-session search, dashboards
  Compliance  cryptographically signed audit manifests, framework mapping,
              escalation policies, RBAC/SSO (org-managed)

Activation, for now:
  * env var   SUNYTE_LICENSE=<token>
  * or file   <project>/.sunyte/license.key

A <token> is either a bare tier name ("team" / "compliance") for self-hosted
use, or a signed token of the form `sunyte-<tier>-<sig>` issued by
`sunyte tier issue <tier>`. Replace `_verify` with a real check against a
licensing service when there is one — that is the only seam that needs to move.
"""

import os
import hashlib

from sunyte.config import sunyte_dir

TIERS = ("free", "team", "compliance")
DEFAULT_UPGRADE_URL = "https://github.com/Sunyte/Sunyte#pricing"


def upgrade_url() -> str:
    """Where 'upgrade / pricing' links point. Overridable so the plugin doesn't
    have to advertise a fixed GitHub repo: SUNYTE_UPGRADE_URL env var, then the
    `upgrade_url` config setting, then the default."""
    env = os.environ.get("SUNYTE_UPGRADE_URL", "").strip()
    if env:
        return env
    try:
        from sunyte.config import load_config
        configured = (load_config().get("upgrade_url") or "").strip()
        if configured:
            return configured
    except Exception:
        pass
    return DEFAULT_UPGRADE_URL

# Not a real secret — it only gates locally-issued scaffold tokens. A hosted
# licensing service would verify signatures server-side instead.
_SCAFFOLD_SECRET = "sunyte-scaffold-v1"


def _license_file() -> str:
    return os.path.join(sunyte_dir(), "license.key")


def _sig(tier: str) -> str:
    return hashlib.sha256((tier + _SCAFFOLD_SECRET).encode("utf-8")).hexdigest()[:12]


def issue_token(tier: str) -> str:
    tier = tier.strip().lower()
    if tier not in TIERS:
        raise ValueError(f"Unknown tier '{tier}'. Choose from: {', '.join(TIERS)}")
    return f"sunyte-{tier}-{_sig(tier)}"


def _verify(token: str):
    token = (token or "").strip()
    if not token:
        return None
    if token.lower() in TIERS:
        return token.lower()  # bare tier name, self-hosted
    parts = token.split("-")
    if len(parts) == 3 and parts[0] == "sunyte" and parts[1] in TIERS:
        if parts[2] == _sig(parts[1]):
            return parts[1]
    return None


def _read_token() -> str:
    token = os.environ.get("SUNYTE_LICENSE", "").strip()
    if token:
        return token
    try:
        with open(_license_file(), "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def get_tier() -> str:
    return _verify(_read_token()) or "free"


def activate(token: str) -> str:
    tier = _verify(token)
    if not tier:
        raise ValueError("That license token is not valid.")
    os.makedirs(sunyte_dir(), exist_ok=True)
    with open(_license_file(), "w", encoding="utf-8") as f:
        f.write(token.strip() + "\n")
    return tier


def _rank(tier: str) -> int:
    return TIERS.index(tier) if tier in TIERS else 0


def at_least(required: str) -> bool:
    return _rank(get_tier()) >= _rank(required)


def gate(required: str, feature: str) -> bool:
    """True if allowed. Otherwise prints a one-line upgrade notice and returns False."""
    if at_least(required):
        return True
    current = get_tier().capitalize()
    print(
        f"[sunyte] {feature} needs the {required.capitalize()} tier - you're on {current}.\n"
        f"         Pricing & upgrade: {upgrade_url()}"
    )
    return False
