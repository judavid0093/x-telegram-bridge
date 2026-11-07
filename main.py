import os
import json
import html
import mimetypes
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

# CONFIGURACIÓN
FEED_URL = "https://fxtwitter.com/tothonoo/media.xml"
STATE_FILE = Path("state.json")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# TUS 5 DESCRIPCIONES PERSONALIZADAS
DESCRIPTIONS = [
    "x.com/i/lists/1894050325029421072",
    "x.com/i/lists/1855938515395051530",
    "x.com/i/lists/1998969343120482610",
    "x.com/tothonoo  x.com/tothonoo93",
    "linktr.ee/kevinshir0",
]


def save_state(state):
    """Guarda el progreso para no repetir publicaciones ni descripciones."""
    temp_file = STATE_FILE.with_suffix(".tmp")
    temp_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    temp_file.replace(STATE_FILE)


def load_state():
    if not STATE_FILE.exists():
        return {
            "last_id": None,
            "caption_index": 0
        }

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))

    # Compatibilidad con el state.json anterior
    if isinstance(state, str):
        state = {"last_id": state}

    state.setdefault("last_id", None)
    state.setdefault("caption_index", 0)

    return state


def fetch_feed():
    request = urllib.request.Request(
        FEED_URL,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        root = ET.fromstring(response.read())

    entries = []

    for item in root.findall(".//item"):
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link).strip()

        media_url = ""
        media_type = ""

        # Busca archivos adjuntos en enclosure y Media RSS.
        for element in item.iter():
            tag = element.tag.split("}")[-1].lower()

            if tag == "enclosure" and not media_url:
                media_url = element.get("url", "")
                media_type = element.get("type", "")

            elif tag == "content" and not media_url:
                media_url = element.get("url", "")
                media_type = element.get("type", "")

        if guid and media_url:
            entries.append({
                "id": guid,
                "link": link,
                "media_url": media_url,
                "media_type": media_type
            })

    print(f"Publicaciones multimedia encontradas: {len(entries)}")
    return entries


def send_telegram(entry, caption):
    media_url = entry["media_url"]
    declared_type = entry.get("media_type", "").lower()

    media_request = urllib.request.Request(
        media_url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(media_request, timeout=120) as response:
        media_data = response.read()
        content_type = response.headers.get(
            "Content-Type", ""
        ).split(";")[0].lower()

    # Si el servidor no informa el tipo, intenta deducirlo.
    if not content_type or content_type == "application/octet-stream":
        content_type = declared_type

    if not content_type or content_type == "application/octet-stream":
        guessed_type, _ = mimetypes.guess_type(media_url)
        content_type = guessed_type or ""

    if content_type.startswith("image/gif"):
        method = "sendAnimation"
        field = "animation"
        filename = "publication.gif"

    elif content_type.startswith("image/"):
        method = "sendPhoto"
        field = "photo"
        filename = "publication.jpg"

    elif content_type.startswith("video/"):
        method = "sendVideo"
        field = "video"
        filename = "publication.mp4"

    else:
        raise RuntimeError(
            f"Tipo multimedia no compatible: {content_type}"
        )

    # Límites habituales de Telegram para estos archivos.
    if method == "sendPhoto" and len(media_data) > 10 * 1024 * 1024:
        raise RuntimeError("La foto supera el límite de 10 MB de Telegram.")

    if method == "sendVideo" and len(media_data) > 50 * 1024 * 1024:
        raise RuntimeError("El video supera el límite de 50 MB de Telegram.")

    boundary = "----TelegramBoundary987654321"

    parts = [
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        f"{CHAT_ID}\r\n",

        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="caption"\r\n\r\n'
        f"{caption}\r\n",

        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; '
        f'filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ]

    body = "".join(parts).encode("utf-8")
    body += media_data
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        }
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.loads(response.read().decode("utf-8"))

    if not result.get("ok"):
        raise RuntimeError(f"Error de Telegram: {result}")

    print(f"Multimedia enviado correctamente: {entry['id']}")


def main():
    state = load_state()
    entries = fetch_feed()

    if not entries:
        print("No se encontraron publicaciones con multimedia.")
        return

    last_id = state["last_id"]

    # Primera ejecución: establece una línea base sin enviar publicaciones antiguas.
    if not last_id:
        state["last_id"] = entries[0]["id"]
        save_state(state)
        print("Primera ejecución: línea base guardada.")
        return

    # El feed está ordenado de más reciente a más antiguo.
    old_position = next(
        (i for i, entry in enumerate(entries)
         if entry["id"] == last_id),
        None
    )

    if old_position is None:
        print("No se encontró la última publicación guardada.")
        print("Se actualiza la línea base para evitar duplicados.")
        state["last_id"] = entries[0]["id"]
        save_state(state)
        return

    # Solo publicaciones nuevas, enviadas de la más antigua a la más reciente.
    new_entries = list(reversed(entries[:old_position]))

    if not new_entries:
        print("No hay publicaciones nuevas.")
        return

    print(f"Publicaciones nuevas para enviar: {len(new_entries)}")

    for entry in new_entries:
        index = state["caption_index"] % len(DESCRIPTIONS)
        caption = DESCRIPTIONS[index]

        # Si falla el envío, no avanza el índice ni guarda esa publicación.
        send_telegram(entry, caption)

        state["last_id"] = entry["id"]
        state["caption_index"] = (index + 1) % len(DESCRIPTIONS)
        save_state(state)

        print(f"Descripción utilizada: {index + 1}")


if __name__ == "__main__":
    main()
