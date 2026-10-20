"""Переписки из zip-архива: один .txt на чат."""
import datetime as dt
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .io_utils import decode, find_file, warn, zip_with_txt
from .parsing import DataFormatError, parse_datetime

MANAGER = "Менеджер"
CLIENT = "Клиент"

HEADER_RE = re.compile(r"^\s*Чат\s+(\S+)")
# [01.02.2030 12:00] Менеджер: текст — формат даты внутри скобок любой, понятный parse_datetime
MESSAGE_RE = re.compile(r"^\s*\[([^\]]+)\]\s*([^:]+?)\s*:\s*(.*)$")
# строка без [времени], но похожая на начало сообщения — не продолжение предыдущего
LOOKS_LIKE_MESSAGE_RE = re.compile(r"^\s*(?:\[|\d{1,4}[./-]\d{1,2}[./-]\d{1,4}|(?:менеджер|клиент)\s*:)",
                                   re.IGNORECASE)


@dataclass
class Message:
    time: dt.datetime
    speaker: str   # MANAGER или CLIENT
    text: str


@dataclass
class Chat:
    chat_id: str
    header: str
    messages: list = field(default_factory=list)


def _speaker(raw, where):
    s = raw.strip().lower()
    if s.startswith("менеджер"):
        return MANAGER
    if s.startswith("клиент"):
        return CLIENT
    raise DataFormatError(f"{where}: непонятный автор сообщения '{raw}'")


def parse_chat(name, text):
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        raise DataFormatError(f"{name}: пустой файл")
    header = HEADER_RE.match(lines[0])
    chat_id = header[1] if header else PurePosixPath(name).stem
    chat = Chat(chat_id=chat_id, header=lines[0] if header else "")

    for i, line in enumerate(lines[1:] if header else lines, start=2 if header else 1):
        m = MESSAGE_RE.match(line)
        if m:
            try:
                time = parse_datetime(m[1])
            except DataFormatError as e:
                raise DataFormatError(f"{name}:{i}: {e}") from None
            chat.messages.append(Message(time, _speaker(m[2], f"{name}:{i}"), m[3].strip()))
        elif chat.messages and not LOOKS_LIKE_MESSAGE_RE.match(line):
            chat.messages[-1].text += "\n" + line.strip()  # продолжение многострочного сообщения
        else:
            raise DataFormatError(f"{name}:{i}: строка не похожа на сообщение: '{line}'")

    times = [msg.time for msg in chat.messages]
    if times != sorted(times):
        warn(f"{name}: сообщения не по порядку времени — упорядочены по времени")
        chat.messages.sort(key=lambda msg: msg.time)  # sort стабилен: внутри минуты — порядок файла
    return chat


def load(data_dir):
    path = find_file(data_dir, (".zip",), zip_with_txt, "Архив переписок")
    chats = []
    with zipfile.ZipFile(path) as zf:
        for info in sorted(zf.infolist(), key=lambda i: i.filename):
            if info.is_dir() or not info.filename.lower().endswith(".txt"):
                continue
            chats.append(parse_chat(info.filename, decode(zf.read(info))))
    ids = [c.chat_id for c in chats]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise DataFormatError(f"повторяющиеся ID чатов: {sorted(duplicates)}")
    return chats
