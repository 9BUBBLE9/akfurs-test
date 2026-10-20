"""Чтение сырых файлов: поиск по содержимому, кодировка, разделитель."""
import csv
import io
import sys
import zipfile
from pathlib import Path

import openpyxl
import pandas as pd

from .parsing import DataFormatError

ENCODINGS = ("utf-8-sig", "cp1251")
HEADER_SEARCH_LINES = 20


def warn(msg):
    print(f"[warn] {msg}", file=sys.stderr)


def find_file(data_dir, suffixes, matches, what):
    """Ровно один файл с нужным расширением, подходящий по содержимому, иначе ошибка.

    Имя файла не важно: новая выгрузка может называться как угодно.
    """
    if not Path(data_dir).is_dir():
        raise FileNotFoundError(f"папка с данными '{data_dir}' не найдена — создайте её и положите "
                                f"туда файлы задания (см. README, раздел «Запуск», шаг «Данные»)")
    candidates = sorted(p for p in Path(data_dir).iterdir()
                        if p.is_file() and p.suffix.lower() in suffixes)
    found = [p for p in candidates if matches(p)]
    if len(found) != 1:
        names = [p.name for p in found] or [p.name for p in candidates]
        raise FileNotFoundError(f"{what}: в {data_dir} ожидался ровно один подходящий файл "
                                f"({'/'.join(suffixes)}), найдено {len(found)}: {names}")
    return found[0]


def csv_with_columns(*columns):
    """Проверка для find_file: в первых строках CSV есть заголовок со всеми колонками."""
    def matches(path):
        try:
            head = decode(path.read_bytes()).splitlines()[:HEADER_SEARCH_LINES]
        except ValueError:
            return False
        return any(all(c in line for c in columns) for line in head)
    return matches


def excel_with_sheet(sheet):
    def matches(path):
        try:
            wb = openpyxl.load_workbook(path, read_only=True)
        except Exception:  # повреждённый или не-Excel файл просто не подходит
            return False
        try:
            return sheet in wb.sheetnames
        finally:
            wb.close()
    return matches


def zip_with_txt(path):
    try:
        with zipfile.ZipFile(path) as zf:
            return any(n.lower().endswith(".txt") for n in zf.namelist())
    except zipfile.BadZipFile:
        return False


def decode(raw):
    for enc in ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise DataFormatError(f"не удалось определить кодировку, пробовали {ENCODINGS}")


def read_csv_text(path, header_marker):
    """CSV как таблица строк (dtype=str).

    header_marker — название колонки, по которому ищется строка заголовка:
    выше неё бывают служебные строки (например, «Выписка по счёту ...»).
    """
    text = decode(Path(path).read_bytes())
    lines = text.splitlines()
    header_idx = next((i for i, l in enumerate(lines) if header_marker in l), None)
    if header_idx is None:
        raise DataFormatError(f"в {path} нет строки заголовка с '{header_marker}'")
    body = "\n".join(lines[header_idx:])
    delimiter = csv.Sniffer().sniff(lines[header_idx], delimiters=";,\t|").delimiter
    df = pd.read_csv(io.StringIO(body), sep=delimiter, dtype=str, keep_default_na=False,
                     skip_blank_lines=False)
    df.columns = [c.strip() for c in df.columns]
    df["source_row"] = df.index + header_idx + 2  # номер строки в исходном файле
    data_cols = df.columns.drop("source_row")
    is_blank = df[data_cols].apply(lambda col: col.str.strip() == "").all(axis=1)
    return df[~is_blank].reset_index(drop=True)


def require_columns(df, columns, source):
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise DataFormatError(f"{source}: нет колонок {missing}, есть {list(df.columns)}")


def read_excel_table(path, sheet, header_marker):
    """Лист Excel как таблица; строка заголовка — первая, где есть header_marker.

    Скрытые листы читаются так же, как видимые.
    """
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    header_rows = [i for i, row in raw.iterrows()
                   if any(str(v).strip() == header_marker for v in row)]
    if not header_rows:
        raise DataFormatError(f"{path} [{sheet}]: нет строки заголовка с '{header_marker}'")
    h = header_rows[0]
    df = raw.iloc[h + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[h]]
    return df.dropna(how="all").reset_index(drop=True)
