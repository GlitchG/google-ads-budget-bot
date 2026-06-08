"""Minimal Telegram sender (advisory bot — no buttons needed)."""
from __future__ import annotations

import requests

import config

API = "https://api.telegram.org/bot{token}/{method}"
LIMIT = 4096


def _call(method: str, **params) -> dict:
    url = API.format(token=config.TELEGRAM_BOT_TOKEN, method=method)
    resp = requests.post(url, json=params, timeout=40).json()
    if not resp.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {resp}")
    return resp.get("result", {})


def send(text: str) -> None:
    """Send, splitting on blank lines if over Telegram's 4096-char limit."""
    for chunk in _chunks(text):
        _call("sendMessage", chat_id=config.TELEGRAM_CHAT_ID, text=chunk,
              parse_mode="HTML", disable_web_page_preview=True)


def _chunks(text: str):
    if len(text) <= LIMIT:
        yield text
        return
    buf = ""
    for block in text.split("\n\n"):
        if len(buf) + len(block) + 2 > LIMIT:
            yield buf
            buf = ""
        buf += block + "\n\n"
    if buf.strip():
        yield buf


def send_buttons(text: str, keyboard: list) -> int:
    """Send a message with an inline keyboard. Returns message_id."""
    res = _call("sendMessage", chat_id=config.TELEGRAM_CHAT_ID, text=text,
                parse_mode="HTML", disable_web_page_preview=True,
                reply_markup={"inline_keyboard": keyboard})
    return res["message_id"]


def edit(message_id: int, text: str) -> None:
    _call("editMessageText", chat_id=config.TELEGRAM_CHAT_ID, message_id=message_id,
          text=text, parse_mode="HTML", disable_web_page_preview=True,
          reply_markup={"inline_keyboard": []})


def answer_callback(callback_id: str, text: str = "") -> None:
    try:
        _call("answerCallbackQuery", callback_query_id=callback_id, text=text)
    except RuntimeError:
        pass


def get_updates(offset, timeout: int = 30):
    url = API.format(token=config.TELEGRAM_BOT_TOKEN, method="getUpdates")
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    return requests.get(url, params=params, timeout=timeout + 10).json().get("result", [])
