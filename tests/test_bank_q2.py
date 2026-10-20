from pathlib import Path

import pytest

from akfurs import bank, catalog, crm, q2
from akfurs.parsing import DataFormatError

BANK_HEADER = ["Выписка по счёту 00000000000000000000;;;;;;",
               "Дата операции;Время;Сумма;Валюта;Тип;Контрагент;Назначение платежа"]


def write_bank(path, rows):
    Path(path).write_bytes(("\r\n".join([*BANK_HEADER, *rows]) + "\r\n").encode("cp1251"))


@pytest.mark.parametrize("purpose, expected", [
    ("Оплачиваю заказ A-04321", [4321]),
    ("Заказ А-04391 (жилет), оплата", [4391]),       # кириллическая А
    ("A4877 доплата", [4877]),
    ("зак. 4528", [4528]),
    ("Аванс заказ 4775, тел. +7 900 000-00-00", [4775]),  # телефон не номер заказа
    ("по счету №4828 от 01.02.2030", [4828]),                  # дата счёта не номер заказа
    ("Счёт № 04991 от 07.05.2030. Без НДС", [4991]),
    ("Возврат клиенту, заказ A-04775", [4775]),
    ("Без назначения", []), ("за изделие", []), ("Платёж по контракту", []), ("Внесение наличных", []),
    ("оплата 2 шт по 500", []),        # «а» в конце слова перед числом — не код заказа
    ("Оплачиваю заказы A-04012 и a-4013", [4012, 4013]),
])
def test_order_candidates(purpose, expected):
    assert bank.order_candidates(purpose) == expected


def test_signed_money():
    assert bank.parse_signed_money("-2 345 600,00") == -2_345_600
    assert bank.parse_signed_money("120 000,00") == 120_000


def test_load_bank(tmp_path):
    write_bank(tmp_path / "02_bank_statement_rub.csv", [
        "03.03.2030;10:15;120 000,00;RUR;Поступление;Тестова А.;Аванс заказ 7, тел. +7 900 000-00-00",
        "",  # пустая строка не сбивает нумерацию
        "04.03.2030;11:20;-120 000,00;RUR;Списание;Тестова А.;Возврат клиенту, заказ A-00007",
    ])
    df = bank.load(tmp_path)
    assert list(df[bank.AMOUNT]) == [120_000, -120_000]
    assert list(df[bank.TYPE]) == ["Поступление", "Списание"]
    assert list(df[bank.SOURCE_ROW]) == [3, 5]


@pytest.mark.parametrize("row, message", [
    ("05.03.2030;09:00;-100,00;RUR;Поступление;X;Без назначения", "знак суммы"),
    ("05.03.2030;09:00;100,00;USD;Поступление;X;Без назначения", "валюты"),
    ("05.03.2030;09:00;100,00;RUR;Трансфер;X;Без назначения", "типа операции"),
    ("5 мар;09:00;100,00;RUR;Поступление;X;Без назначения", "даты"),
])
def test_load_bank_bad(tmp_path, row, message):
    write_bank(tmp_path / "02_bank.csv", [row])
    with pytest.raises(DataFormatError, match=message):
        bank.load(tmp_path)


def test_q2(data_dir):
    # в data_dir заказы 7 (Оплачен) и 8 (Отменён)
    write_bank(data_dir / "02_bank_statement_rub.csv", [
        "02.01.2030;10:00;100 000,00;RUR;Поступление;А;Оплачиваю заказ A-00008",     # отменённый, но существует
        "03.01.2030;10:00;50 123,00;RUR;Поступление;Б;Оплачиваю заказ A-09999",      # нет такого заказа
        "04.01.2030;10:00;25 000,50;RUR;Поступление;В;за изделие",                    # без номера
        "05.01.2030;10:00;-90 000,00;RUR;Списание;Г;Возврат по заказу A-00007",    # списание не оплата
    ])
    orders = crm.load_clean(data_dir, catalog.load(data_dir))
    result = q2.solve(orders, bank.load(data_dir))
    assert result["q2a_paid_orders_without_payment"] == [7]
    assert result["q2b_unidentified_payments_count"] == 2
    assert result["q2b_unidentified_payments_sum_rub"] == 75_123.5


def test_ambiguous_payment_is_unidentified(data_dir, capsys):
    write_bank(data_dir / "02_bank_statement_rub.csv", [
        "02.01.2030;10:00;100 000,00;RUR;Поступление;А;Оплата заказов A-00007 и A-00008",
    ])
    orders = crm.load_clean(data_dir, catalog.load(data_dir))
    result = q2.solve(orders, bank.load(data_dir))
    assert result["q2b_unidentified_payments_count"] == 1
    assert "несколько заказов" in capsys.readouterr().err
