"""Строгий разбор значений: незнакомый формат -> DataFormatError, а не тихий пропуск."""
import datetime as dt
import re

from .dictionaries import MONTHS


class DataFormatError(ValueError):
    pass


def clean_spaces(value):
    """Неразрывные и прочие пробелы -> обычный, без краёв и повторов."""
    return re.sub(r"\s+", " ", str(value).replace(" ", " ").replace(" ", " ")).strip()


def norm_key(value):
    """Ключ для поиска в словарях: без регистра, ё=е, единичные пробелы."""
    return clean_spaces(value).lower().replace("ё", "е")


def lookup(value, mapping, what):
    key = norm_key(value)
    if key not in mapping:
        raise DataFormatError(f"незнакомое значение {what}: '{value}' "
                              f"(добавьте '{key}' в akfurs/dictionaries.py)")
    return mapping[key]


# ---------- даты ----------

EXCEL_EPOCH = dt.date(1899, 12, 30)
SLASH_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def infer_slash_order(values):
    """Порядок в датах вида NN/NN/YYYY по самим данным: 'dmy' или 'mdy'.

    Если где-то первое число > 12 — это день; если второе > 12 — месяц идёт первым.
    Противоречие — ошибка. Если однозначных дат нет, считаем 'dmy' (российская запись).
    """
    first_is_day = second_is_day = False
    for v in values:
        m = SLASH_RE.match(clean_spaces(v))
        if m:
            first_is_day |= int(m.group(1)) > 12
            second_is_day |= int(m.group(2)) > 12
    if first_is_day and second_is_day:
        raise DataFormatError("даты через '/' противоречат друг другу: есть и ДД/ММ, и ММ/ДД")
    return "mdy" if second_is_day else "dmy"


def parse_date(value, slash_order="dmy"):
    s = clean_spaces(value)
    try:
        if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s):
            return dt.date(int(m[1]), int(m[2]), int(m[3]))
        if m := re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s):
            return dt.date(int(m[3]), int(m[2]), int(m[1]))
        if m := SLASH_RE.fullmatch(s):
            a, b = int(m[1]), int(m[2])
            day, month = (a, b) if slash_order == "dmy" else (b, a)
            return dt.date(int(m[3]), month, day)
        if m := re.fullmatch(r"(\d{1,2}) ([а-яё]+)\.? (\d{4})", s.lower()):
            month = MONTHS.get(m[2][:3])
            if month:
                return dt.date(int(m[3]), month, int(m[1]))
        if re.fullmatch(r"\d{5}", s):  # серийный номер даты Excel
            return EXCEL_EPOCH + dt.timedelta(days=int(s))
    except ValueError as e:  # несуществующая дата, например 31.02
        raise DataFormatError(f"некорректная дата '{value}': {e}") from None
    raise DataFormatError(f"непонятный формат даты: '{value}'")


def parse_datetime(value):
    s = clean_spaces(value)
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise DataFormatError(f"непонятный формат даты-времени: '{value}'")


# ---------- числа и деньги ----------

MONEY_PATTERNS = [
    # 2 200 000 / 2 200 000,00 / 2 200 000.00
    (re.compile(r"\d{1,3}(?: \d{3})+(?:[.,]\d{1,2})?"), lambda s: s.replace(" ", "").replace(",", ".")),
    # 245,000.00 / 1,250,000 (американская запись; одна группа без копеек — неоднозначно)
    (re.compile(r"\d{1,3}(?:,\d{3})+\.\d{1,2}|\d{1,3}(?:,\d{3}){2,}"), lambda s: s.replace(",", "")),
    # 2.183.000 (точки как разделитель тысяч, минимум две группы)
    (re.compile(r"\d{1,3}(?:\.\d{3}){2,}"), lambda s: s.replace(".", "")),
    # 140000,00 / 700.00 / 50000
    (re.compile(r"\d+(?:[.,]\d{1,2})?"), lambda s: s.replace(",", ".")),
]
SCALED_RE = re.compile(r"(\d+(?:[.,]\d+)?) ?(млн|тыс)\.?")
SCALES = {"млн": 1_000_000, "тыс": 1_000}


def parse_money(value):
    """Сумма в рублях (float, до копеек). Неоднозначные записи вроде '1,600' — ошибка."""
    s = clean_spaces(value).lower()
    if m := SCALED_RE.fullmatch(s):
        return round(float(m[1].replace(",", ".")) * SCALES[m[2]], 2)
    for pattern, normalize in MONEY_PATTERNS:
        if pattern.fullmatch(s):
            return round(float(normalize(s)), 2)
    raise DataFormatError(f"непонятный формат суммы: '{value}'")


def parse_quantity(value):
    s = clean_spaces(value)
    if not re.fullmatch(r"\d+", s) or int(s) == 0:
        raise DataFormatError(f"некорректное количество: '{value}'")
    return int(s)


def parse_discount(value, line_gross):
    """Скидка в рублях на всю строку. 'N%' — процент от Цена×Кол-во, число — рубли."""
    s = clean_spaces(value)
    if not s:
        return 0.0
    if m := re.fullmatch(r"(\d+(?:[.,]\d+)?) ?%", s):
        pct = float(m[1].replace(",", "."))
        if pct > 100:
            raise DataFormatError(f"скидка больше 100%: '{value}'")
        discount = round(line_gross * pct / 100, 2)
    else:
        discount = parse_money(s)
    if discount > line_gross:
        raise DataFormatError(f"скидка '{value}' больше суммы строки {line_gross}")
    return discount


CLIENT_RE = re.compile(r"(?:cl|кл)[ -]?(\d+)")


def parse_client_id(value):
    """CL-90042 / cl90042 / КЛ-90042 / CL 90042 -> 90042."""
    m = CLIENT_RE.fullmatch(norm_key(value))
    if not m:
        raise DataFormatError(f"непонятный формат клиента: '{value}'")
    return int(m[1])


def parse_article(value):
    s = clean_spaces(value).upper()
    if not re.fullmatch(r"[A-Z0-9-]+", s):
        raise DataFormatError(f"непонятный артикул: '{value}'")
    return s


# A-00075, А-75 (кириллица), a-75, A75, 75 -> 75
ORDER_RE = re.compile(r"[AaАа]? ?-? ?(\d+)")


def parse_order_number(value):
    m = ORDER_RE.fullmatch(clean_spaces(value))
    if not m:
        raise DataFormatError(f"непонятный номер заказа: '{value}'")
    return int(m[1])


def parse_line_number(value):
    s = clean_spaces(value)
    if not re.fullmatch(r"\d+", s):
        raise DataFormatError(f"некорректный № строки: '{value}'")
    return int(s)
