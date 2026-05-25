import json
import logging
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger("DankBot.Webhook")


def send_webhook(url: str, content: str = "", embed: dict = None) -> dict:
    """Send Discord webhook message. Returns {'ok': bool, 'error': str or None}."""
    if not url.startswith("https://discord.com/api/webhooks/"):
        return {"ok": False, "error": "invalid_url"}

    payload = {"content": content}
    if embed:
        payload["embeds"] = [embed]

    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "DankBot/1.0")

    try:
        resp = urlopen(req, timeout=10)
        resp.read()
        return {"ok": True, "error": None}
    except HTTPError as e:
        err = f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"
        logger.error(f"Webhook HTTP error: {err}")
        return {"ok": False, "error": err}
    except URLError as e:
        err = f"Connection failed: {e.reason}"
        logger.error(f"Webhook URL error: {err}")
        return {"ok": False, "error": err}
    except Exception as e:
        logger.error(f"Webhook send failed: {e}")
        return {"ok": False, "error": str(e)}


def test_webhook(url: str) -> dict:
    """Send test message to verify webhook URL works."""
    embed = {
        "title": "Dank Memer Bot — Test",
        "description": "Webhook configured correctly.",
        "color": 0x89B4FA,
        "footer": {"text": f"Test sent at {time.strftime('%H:%M:%S')}"},
    }
    return send_webhook(url, content="", embed=embed)


def build_session_embed(stats: dict, duration_secs: int) -> dict:
    """Build Discord embed from session statistics."""
    m, s = divmod(int(duration_secs), 60)
    h, m = divmod(m, 60)
    duration_str = f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

    lines = [
        f"**Casts:** {stats.get('casts', 0)}",
        f"**Catches:** {stats.get('catches', 0)}",
        f"**Sells:** {stats.get('sells', 0)}",
        f"**Rare Kept:** {stats.get('rare_kept', 0)}",
        f"**Errors:** {stats.get('errors', 0)}",
        f"**Estimated Earnings:** {stats.get('earnings', 0)} coins",
    ]

    return {
        "title": "Session Summary",
        "description": "\n".join(lines),
        "color": 0xA6E3A1,
        "fields": [
            {"name": "Duration", "value": duration_str, "inline": True},
            {"name": "Status", "value": "Completed", "inline": True},
        ],
        "footer": {"text": f"Session ended {time.strftime('%Y-%m-%d %H:%M')}"},
    }
