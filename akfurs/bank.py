"""Банковская выписка: разбор операций и поиск номера заказа в назначении платежа."""
import re

from .dictionaries import CURRENCIES, OPERATION_TYPES, TYPE_INCOMING
from .io_utils import find_file, read_csv_text, require_columns
from .parsing import DataFormatError, clean_spaces, lookup, parse_date, parse_money

BANK_PATTERN = "*bank*.csv"

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
#   «зак. 75», «… заказ 75, тел. …», «по счету №75», «Счёт № 00075»    -> слово + число.
# Числа без такого контекста (телефоны, даты счетов, суммы) не берутся.
ORDER_CODE_RE = re.compile(r"(?<![0-9A-Za-zА-Яа-яЁё])[AaАа]-?(\d+)(?!\d)")
KEYWORD_RE = re.compile(
    r"(?<![А-Яа-яЁё])(?:заказ[а-яё]*|зак\.?|сч[её]т[а-яё]*|сч\.)\s*(?:№\s*)?(?:[AaАа]-?)?(\d+)(?!\d)",
    re.IGNORECASE,
)


def order_candidates(purpose):
    """Номера заказов, упомянутые в назначении платежа (без ведущих нулей, по порядку)."""
    s = clean_spaces(purpose)
    found = [int(m.group(1)) for rx in (ORDER_CODE_RE, KEYWORD_RE) for m in rx.finditer(s)]
    return list(dict.fromkeys(found))


def parse_signed_money(value):
    s = clean_spaces(value)
    sign = -1 if s[:1] in ("-", "−") else 1
    return sign * parse_money(s.lstrip("-−").strip())


def load(data_dir):
    df = read_csv_text(find_file(data_dir, BANK_PATTERN), header_marker=COL_PURPOSE)
    require_columns(df, REQUIRED, "Выписка")
    df = df[df[COL_DATE].str.strip() != ""].copy()  # итоговые/пустые строки

    errors = []
    dates, amounts, types = [], [], []
    for row, date, amount, currency, op_type in zip(
            df[SOURCE_ROW], df[COL_DATE], df[COL_AMOUNT], df[COL_CURRENCY], df[COL_TYPE]):
        try:
            lookup(currency, CURRENCIES, "валюты")
            d, a, t = parse_date(date), parse_signed_money(amount), lookup(op_type, OPERATION_TYPES,
                                                                            "типа операции")
            if (a > 0) != (t == TYPE_INCOMING):
                raise DataFormatError(f"знак суммы {amount} не соответствует типу '{op_type}'")
        except DataFormatError as e:
            errors.append(f"строка {row}: {e}")
            d = a = t = None
        dates.append(d), amounts.append(a), types.append(t)
    if errors:
        raise DataFormatError(f"Выписка: {len(errors)} ошибок формата:\n  " + "\n  ".join(errors[:30]))

    df[DATE], df[AMOUNT], df[TYPE] = dates, amounts, types
    df[ORDER_CANDIDATES] = df[COL_PURPOSE].map(order_candidates)
    return df.reset_index(drop=True)
