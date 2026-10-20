import datetime as dt

import pytest

from akfurs.dictionaries import CURRENCIES, STATUSES
from akfurs.parsing import (
    DataFormatError, infer_slash_order, lookup, parse_article, parse_client_id, parse_date,
    parse_datetime, parse_discount, parse_line_number, parse_money, parse_order_number,
    parse_quantity,
)

D = dt.date


@pytest.mark.parametrize("raw, expected", [
    ("A-00075", 75), ("А-75", 75), ("a-75", 75), ("A75", 75), (" a-811", 811), ("A00512", 512),
])
def test_order_number(raw, expected):
    assert parse_order_number(raw) == expected


@pytest.mark.parametrize("raw", ["B-75", "A-75-1", "", "заказ 75", "A 7 5"])
def test_order_number_bad(raw):
    with pytest.raises(DataFormatError):
        parse_order_number(raw)


@pytest.mark.parametrize("raw, expected", [
    ("2025-03-03", D(2025, 3, 3)),
    ("09.01.2026", D(2026, 1, 9)),
    ("13/02/2025", D(2025, 2, 13)),
    ("23 сен 2030", D(2030, 9, 23)),
    ("1 мая 2025", D(2025, 5, 1)),
    ("31 янв 2026", D(2026, 1, 31)),
    ("45658", D(2025, 1, 1)),  # серийный номер Excel
    ("45752", D(2025, 4, 5)),
])
def test_date(raw, expected):
    assert parse_date(raw) == expected


def test_date_slash_order():
    assert parse_date("02/11/2025", "dmy") == D(2025, 11, 2)
    assert parse_date("02/11/2025", "mdy") == D(2025, 2, 11)


@pytest.mark.parametrize("raw", ["2025/03/03", "31.02.2025", "23 foo 2026", "вчера", "", "123"])
def test_date_bad(raw):
    with pytest.raises(DataFormatError):
        parse_date(raw)


def test_infer_slash_order():
    assert infer_slash_order(["13/02/2025", "01/02/2025", "2025-01-01"]) == "dmy"
    assert infer_slash_order(["02/13/2025", "01/02/2025"]) == "mdy"
    assert infer_slash_order(["01/02/2025"]) == "dmy"  # неоднозначно -> российская запись
    with pytest.raises(DataFormatError):
        infer_slash_order(["13/02/2025", "02/13/2025"])


def test_datetime():
    assert parse_datetime("2030-01-01 09:05") == dt.datetime(2030, 1, 1, 9, 5)
    with pytest.raises(DataFormatError):
        parse_datetime("01/01/2030 09:05")


@pytest.mark.parametrize("raw, expected", [
    ("2 200 000", 2_200_000), ("2 200 000", 2_200_000), ("245,000.00", 245_000),
    ("140000,00", 140_000), ("700.00", 700), ("50000", 50_000), ("2,48 млн", 2_480_000),
    ("117 тыс.", 117_000), ("2.183.000", 2_183_000), ("1,250,000", 1_250_000),
    ("23 500", 23_500), ("1 234,50", 1234.5),
])
def test_money(raw, expected):
    assert parse_money(raw) == expected


@pytest.mark.parametrize("raw", ["1,600", "74.000", "12 34", "-5000", "abc", "", "1.2.3"])
def test_money_bad(raw):
    with pytest.raises(DataFormatError):
        parse_money(raw)


def test_discount():
    assert parse_discount("", 50_000) == 0
    assert parse_discount("7%", 50_000) == 3_500
    assert parse_discount("10 %", 2 * 19_000) == 3_800  # процент от Цена × Кол-во
    assert parse_discount("800", 2 * 19_000) == 800       # рубли на всю строку
    assert parse_discount("1,600.00", 30_000) == 1_600
    with pytest.raises(DataFormatError):
        parse_discount("150%", 10_000)
    with pytest.raises(DataFormatError):
        parse_discount("20 000", 10_000)  # скидка больше суммы строки
    with pytest.raises(DataFormatError):
        parse_discount("10 руб", 10_000)


def test_quantity_and_line():
    assert parse_quantity("2") == 2
    assert parse_line_number(" 3 ") == 3
    for bad in ["0", "1.5", "", "два"]:
        with pytest.raises(DataFormatError):
            parse_quantity(bad)


@pytest.mark.parametrize("raw, expected", [
    ("CL-90118", 90118), ("cl90068", 90068), ("КЛ-90680", 90680), ("CL 9090", 9090),
])
def test_client(raw, expected):
    assert parse_client_id(raw) == expected


def test_client_bad():
    with pytest.raises(DataFormatError):
        parse_client_id("Иванова")


def test_article():
    assert parse_article(" abcdef01n ") == "ABCDEF01N"
    with pytest.raises(DataFormatError):
        parse_article("RYS PAL")


@pytest.mark.parametrize("raw, expected", [
    ("Оплачен ", "Оплачен"), ("оплачено", "Оплачен"), ("PAID", "Оплачен"),
    ("отменен", "Отменён"), ("Отменён", "Отменён"), ("CANCELLED", "Отменён"),
    ("REFUND", "Возврат"), ("возврат", "Возврат"),
    ("NEW", "В работе"), ("Ждём оплату", "В работе"), ("в работе", "В работе"),
])
def test_status(raw, expected):
    assert lookup(raw, STATUSES, "статуса") == expected


def test_currency():
    assert {lookup(v, CURRENCIES, "валюты") for v in ["RUB", "руб.", "руб", "₽", "RUR"]} == {"RUB"}
    with pytest.raises(DataFormatError):
        lookup("USD", CURRENCIES, "валюты")
