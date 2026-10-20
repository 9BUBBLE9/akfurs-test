"""Регрессия: новые написания, найденные проверкой на «новой версии» данных."""
import datetime as dt
import subprocess
import sys
from pathlib import Path

import pytest

from akfurs import bank, catalog, chats, crm, q2, q4
from akfurs.parsing import DataFormatError, parse_date, parse_money
from conftest import write_catalog, write_crm
from test_bank_q2 import write_bank

ROOT = Path(__file__).resolve().parents[1]


# ---------- CRM ----------

def test_dash_dates_and_currency_in_price():
    assert parse_date("15-03-2030") == dt.date(2030, 3, 15)
    assert parse_date("03-15-2030", "mdy") == dt.date(2030, 3, 15)
    assert parse_money("49 000 ₽") == 49_000
    assert parse_money("49 000 руб.") == 49_000
    with pytest.raises(DataFormatError):
        parse_money("49 000 $")


@pytest.mark.parametrize("raw, expected", [
    ("Отменён клиентом", "Отменён"), ("Возврат средств", "Возврат"),
    ("Оплачено полностью", "Оплачен"), ("Paid in full", "Оплачен"),
    ("Оплачен частично", "В работе"), ("не оплачен", "В работе"), ("Согласование", "В работе"),
])
def test_guess_status(raw, expected):
    assert crm._guess_status(raw)[0] == expected


@pytest.mark.parametrize("raw", ["Белкина Дарья", "Д.Белкина", "белкина д", "  ДАРЬЯ   БЕЛКИНА "])
def test_manager_by_name_parts(data_dir, capsys, raw):
    assert catalog.load(data_dir).canonical_manager(raw) == "Дарья Белкина"


def test_manager_guess_warns_once_and_unknown_fails(data_dir, capsys):
    cat = catalog.load(data_dir)
    cat.canonical_manager("Белкина Дарья")
    cat.canonical_manager("Белкина Дарья")
    assert capsys.readouterr().err.count("Белкина Дарья") == 1
    for bad in ["Белкина", "Дарья Зайцева", "Иван Тестов"]:
        with pytest.raises(DataFormatError):
            cat.canonical_manager(bad)


def test_errors_grouped_by_kind(tmp_path):
    write_catalog(tmp_path / "c.xlsx")
    rows = [f"A-{i};1;2026/01/{i:02d};CL-1;Дарья;IG;KEEP-01;1;50000;руб;;PAID;;2030-01-01 09:00"
            for i in range(1, 6)]
    rows.append("A-9;1;2026-01-10;CL-1;Иван;IG;KEEP-01;1;50000;руб;;PAID;;2030-01-01 09:00")
    write_crm(tmp_path / "01_crm.csv", rows)
    with pytest.raises(DataFormatError) as e:
        crm.load_clean(tmp_path, catalog.load(tmp_path))
    text = str(e.value)
    assert "видов проблем — 2" in text and "5 стр." in text and "Иван" in text


# ---------- поиск файлов по содержимому ----------

def test_files_found_by_content_not_name(data_dir):
    (data_dir / "01_crm_orders_export.csv").rename(data_dir / "заказы_ноябрь.csv")
    (data_dir / "03_catalog.xlsx").rename(data_dir / "справочник.xlsx")
    (data_dir / "лишний.xlsx").write_bytes(b"not an excel file")
    df = crm.load_clean(data_dir, catalog.load(data_dir))
    assert len(df) == 3


def test_two_crm_files_fail(data_dir):
    (data_dir / "copy.csv").write_bytes((data_dir / "01_crm_orders_export.csv").read_bytes())
    with pytest.raises(FileNotFoundError, match="найдено 2"):
        crm.load_raw(data_dir)


# ---------- выписка ----------

@pytest.mark.parametrize("purpose, expected", [
    ("Оплата заказа: 1001", [1001]),
    ("Платёж: заказ #4605", [4605]),
    ("Order A-0921 payment", [921]),
    ("order 75", [75]), ("Invoice № 75", [75]),
    ("Счёт №: 04828", [4828]),
    ("Зачисление с карты 4276 **** 1234", []),
])
def test_new_purpose_formats(purpose, expected):
    assert bank.order_candidates(purpose) == expected


def test_plus_sign_amount():
    assert bank.parse_signed_money("+150 000,00") == 150_000


def test_bare_number_warns(data_dir, capsys):
    write_bank(data_dir / "02_bank.csv", [
        "02.01.2030;10:00;100 000,00;RUR;Поступление;А;Оплата 7, тел. +7 900 000-00-00",
    ])
    orders = crm.load_clean(data_dir, catalog.load(data_dir))
    assert q2.solve(orders, bank.load(data_dir))["q2b_unidentified_payments_count"] == 1
    err = capsys.readouterr().err
    assert "[7]" in err and "проверьте вручную" in err


# ---------- переписки ----------

HEAD = "Чат C0001 | клиент cl1 | заказ A-1 | менеджер Дарья"


def test_iso_timestamps():
    chat = chats.parse_chat("c.txt", "\n".join([
        HEAD, "[2026-10-05 12:00] Клиент: Сколько стоит?", "[05.10.2026 12:05] Менеджер: Здравствуйте"]))
    assert [m.time.minute for m in chat.messages] == [0, 5]


@pytest.mark.parametrize("line", [
    "05/10/2026 12:05 Менеджер: Здравствуйте",   # дата без скобок
    "Менеджер: Здравствуйте",                     # без даты
    "[вчера 12:05] Менеджер: Здравствуйте",      # непонятная дата
])
def test_message_in_unknown_format_fails(line):
    with pytest.raises(DataFormatError):
        chats.parse_chat("c.txt", "\n".join([HEAD, "[05.10.2026 12:00] Клиент: Привет", line]))


@pytest.mark.parametrize("text", [
    "Будем рады видеть вас в шоуруме в субботу!",
    "В какой день вам удобно заехать к нам?",
    "Заходите в шоурум, всё покажем.",
    "Приходите в субботу, подберём модель.",
    "Можно записаться на субботу.",
])
def test_new_invites(text):
    assert q4.is_invite(text)


def test_price_without_unit_after_price_word():
    assert q4.is_price("Цена: 250000")
    assert q4.is_price("Стоимость 1 250 000")
    assert not q4.is_price("Внесите аванс 40%, остаток при выдаче.")
    assert not q4.is_price("Цена зависит от размера, уточню послезавтра в 16:30")


def test_maybe_invite_warns(capsys):
    chat = chats.parse_chat("c.txt", "\n".join([HEAD, "[05.10.2026 12:00] Менеджер: Во сколько вам будет удобно?"]))
    q4.judge(chat)
    assert "похоже на приглашение" in capsys.readouterr().err


# ---------- запуск ----------

def test_cli_reports_data_error_without_traceback(tmp_path):
    write_catalog(tmp_path / "c.xlsx")
    write_crm(tmp_path / "01_crm.csv",
              ["A-1;1;вчера;CL-1;Дарья;IG;KEEP-01;1;50000;руб;;PAID;;2030-01-01 09:00"])
    r = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "solve.py"), str(tmp_path),
                        "-o", str(tmp_path / "out.json")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2
    assert "ОШИБКА В ДАННЫХ" in r.stderr and "Traceback" not in r.stderr
    assert not (tmp_path / "out.json").exists()
