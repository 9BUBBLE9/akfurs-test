"""Чтение сырых файлов: поиск по маске, кодировка, разделитель."""
import csv
import io
import re
import sys
from pathlib import Path

import pandas as pd

ENCODINGS = ("utf-8-sig", "cp1251")


def warn(msg):
    print(f"[warn] {msg}", file=sys.stderr)


def find_file(data_dir, pattern):
    """Ровно один файл в папке по маске, иначе ошибка."""
    found = sorted(Path(data_dir).glob(pattern))
    if len(found) != 1:
        raise FileNotFoundError(f"ожидался один файл '{pattern}' в {data_dir}, найдено: {found}")
    return found[0]


def decode(raw):
    for enc in ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"не удалось определить кодировку, пробовали {ENCODINGS}")


def read_csv_text(path, header_marker):
    """CSV как таблица строк (dtype=str).

    header_marker — название колонки, по которому ищется строка заголовка:
    выше неё бывают служебные строки (например, «Выписка по счёту ...»).
    """
    text = decode(Path(path).read_bytes())
    lines = text.splitlines()
    header_idx = next((i for i, l in enumerate(lines) if header_marker in l), None)
    if header_idx is None:
        raise ValueError(f"в {path} нет строки заголовка с '{header_marker}'")
    body = "\n".join(lines[header_idx:])
    delimiter = csv.Sniffer().sniff(lines[header_idx], delimiters=";,\t|").delimiter
    df = pd.read_csv(io.StringIO(body), sep=delimiter, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    return df


# A-00075, А-75 (кириллица), a-75, A75, 75 -> 75
ORDER_RE = re.compile(r"^[AaАа]?\s*-?\s*(\d+)$")


def parse_order_number(value):
    """Номер заказа как число или None, если формат не распознан."""
    m = ORDER_RE.match(str(value).strip())
    return int(m.group(1)) if m else None
