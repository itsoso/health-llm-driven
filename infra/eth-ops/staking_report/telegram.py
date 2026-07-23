import hashlib
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def delivery_key(report_date: str, chat_id: str) -> str:
    chat_hash = hashlib.sha256(chat_id.encode()).hexdigest()[:16]
    return f"telegram:daily:{report_date}:{chat_hash}"


def send_message(token: str, chat_id: str, text: str, timeout: float = 10) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urlencode({"chat_id": chat_id, "text": text}).encode()
    request = Request(url, data=body)
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
            if response.status != 200 or payload.get("ok") is not True:
                raise RuntimeError("Telegram rejected message")
    except Exception as exc:
        raise RuntimeError("Telegram delivery failed") from exc
