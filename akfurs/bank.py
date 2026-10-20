"""Банковская выписка: разбор операций и поиск номера заказа в назначении платежа."""
import re

from .dictionaries import CURRENCIES, OPERATION_TYPES, TYPE_INCOMING
from .io_utils import csv_with_columns, find_file, read_csv_text, require_columns
from .parsing import (
    DataFormatError, ErrorCollector, clean_spaces, lookup, parse_date, parse_money,
)

COL_DATE = "Дата операции"
COL_AMOUNT = "Сумма"
COL_CURRENCY = "Валюта"
COL_TYPE = "Тип"
COL_COUNTERPARTY = "Контрагент"
COL_PURPOSE = "Назначение платежа"
REQUIRED = [COL_DATE, COL_AMOUNT, COL_CURRENCY, COL_TYPE, COL_PURPOSE]

SOURCE_ROW = "source_row"
DATE = "date"
AMOUNT = "amount"            # со знаком: поступления > 0, списания < 0
TYPE = "type"
ORDER_CANDIDATES = "order_candidates"  # все номера, похожие на номер заказа

# Номер заказа в назначении записывают по-разному:
#   «… заказа A-00075», «… заказу А-75», «A75 доплата»                  -> код с буквой A/А;
#   «зак. 75», «… заказ 75, тел. …», «по счету №75», «Счёт № 00075», «заказа: 1001»,
#   «по заказу #605», «order 75», «invoice 75»                          -> слово + число.
# Числа без такого контекста (телефоны, даты счетов, суммы) не берутся.
ORDER_CODE_RE = re.compile(r"(?<![0-9A-Za-zА-Яа-яЁё])[AaАа]-?(\d+)(?!\d)")
KEYWORD_RE = re.compile(
    r"(?<![А-Яа-яЁёA-Za-z])(?:заказ[а-яё]*|зак\.?|сч[её]т[а-яё]*|сч\.|order|invoice|inv\.?)"
    r"[\s:#№.]*(?:[AaАа]-?)?(\d+)(?!\d)",
    re.IGNORECASE,
)
# отдельное число в назначении без слова «заказ» — повод проверить платёж вручную
BARE_NUMBER_RE = re.compile(r"(?<![\d.,:/+-])\d{1,6}(?!\d|[.,:/-]\d)")
PHONE_OR_DATE_RE = re.compile(r"\+?\d[\d ()-]{8,}\d|\d{1,2}\.\d{1,2}\.\d{2,4}")


def bare_numbers(purpose):
    """Числа в назначении, не похожие на телефон или дату."""
    return [int(n) for n in BARE_NUMBER_RE.findall(PHONE_OR_DATE_RE.sub(" ", clean_spaces(purpose)))]


def order_candidates(purpose):
    """Номера заказов, упомянутые в назначении платежа (без ведущих нулей, по порядку)."""
    s = clean_spaces(purpose)
    found = [int(m.group(1)) for rx in (ORDER_CODE_RE, KEYWORD_RE) for m in rx.finditer(s)]
    return list(dict.fromkeys(found))


def parse_signed_money(value):
    s = clean_spaces(value)
    sign = -1 if s[:1] in ("-", "−") else 1
    return sign * parse_money(s.lstrip("+-−").strip())


def load(data_dir):
    path = find_file(data_dir, (".csv", ".txt"), csv_with_columns(COL_DATE, COL_AMOUNT, COL_PURPOSE),
                     "Банковская выписка")
    df = read_csv_text(path, header_marker=COL_PURPOSE)
    require_columns(df, REQUIRED, "Выписка")
    df = df[df[COL_DATE].str.strip() != ""].copy()  # итоговые/пустые строки

    errors = ErrorCollector()
    errors.apply(df, COL_CURRENCY, lambda v: lookup(v, CURRENCIES, "валюты"), COL_CURRENCY)
    df[DATE] = errors.apply(df, COL_DATE, parse_date, COL_DATE)
    df[AMOUNT] = errors.apply(df, COL_AMOUNT, parse_signed_money, COL_AMOUNT)
    df[TYPE] = errors.apply(df, COL_TYPE, lambda v: lookup(v, OPERATION_TYPES, "типа операции"),
                            COL_TYPE)

    def check_sign(amount, op_type, raw_amount):
        if amount is not None and op_type is not None and (amount > 0) != (op_type == TYPE_INCOMING):
            raise DataFormatError(f"знак суммы '{raw_amount}' не соответствует типу '{op_type}'")
    errors.apply(df, COL_AMOUNT, check_sign, AMOUNT, TYPE, COL_AMOUNT)
    errors.raise_if_any("Выписка")

    df[ORDER_CANDIDATES] = df[COL_PURPOSE].map(order_candidates)
    return df.reset_index(drop=True)
