
import os
import json
import html
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

FEED_URL = "https://fxtwitter.com/tothonoo/feed.xml"
STATE_FILE = Path("state.json")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def fetch_feed():
    request = urllib.request.Request(
        FEED_URL,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())

    items = root.findall(".//item")
    entries = []

    for item in items:
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link).strip()
        title = html.unescape(
            (item.findtext("title") or "Nueva publicación").strip()
        )

        if link and guid:
            entries.append({
                "id": guid,
                "title": title,
                "link": link
            })

    return entries


def load_state():
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8"
    )


def send_telegram(entry):
    message = f"{entry['title']}\n\n{entry['link']}"

    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message
    }).encode()

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=data
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read())

    if not result.get("ok"):
        raise RuntimeError(f"Telegram error: {result}")

    print("Publicado:", entry["link"])


def main():
    entries = fetch_feed()

    if not entries:
        print("No hay publicaciones en el feed.")
        return

    state = load_state()
    last_id = state.get("last_id")

    # Primera ejecución: registrar la publicación más reciente
    # sin enviar publicaciones antiguas.
    if not last_id:
        state["last_id"] = entries[0]["id"]
        save_state(state)
        print("Inicialización completada.")
        return

    ids = [entry["id"] for entry in entries]

    if last_id not in ids:
        print("No se encontró el último registro. "
              "Se establece una nueva referencia.")
        state["last_id"] = entries[0]["id"]
        save_state(state)
        return

    last_index = ids.index(last_id)
    new_entries = entries[:last_index]

    # Enviar primero las publicaciones más antiguas.
    for entry in reversed(new_entries):
        send_telegram(entry)
        state["last_id"] = entry["id"]
        save_state(state)

    print(f"Proceso terminado. Nuevas publicaciones: "
          f"{len(new_entries)}")


if __name__ == "__main__":
    main()
