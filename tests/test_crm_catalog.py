import datetime as dt

import pytest

from akfurs import catalog, crm
from akfurs.parsing import DataFormatError
from conftest import write_catalog, write_crm

D = dt.date


def test_catalog_reads_hidden_sheet_and_renames(data_dir):
    cat = catalog.load(data_dir)
    assert cat.current_article("OLD-01") == "NEW01N"
    assert cat.current_article("KEEP-01") == "KEEP-01"
    assert cat.min_price("NEW01N", D(2025, 12, 31)) == 100_000  # границы периода включительно
    assert cat.min_price("NEW01N", D(2026, 1, 1)) == 110_000
    assert cat.min_price("NEW01N", D(2030, 1, 1)) == 110_000    # «Действует по» пусто
    assert cat.canonical_manager("  и. зайцева ") == "Ирина Зайцева"


def test_catalog_unknown_manager_and_missing_price(data_dir):
    cat = catalog.load(data_dir)
    with pytest.raises(DataFormatError):
        cat.canonical_manager("Иван")
    with pytest.raises(DataFormatError):
        cat.min_price("NEW01N", D(2024, 12, 31))  # раньше первого периода


def test_catalog_rename_chain(tmp_path):
    write_catalog(tmp_path / "c.xlsx", renames=[("A-1", "B-1", None), ("B-1", "NEW01N", None)])
    assert catalog.load(tmp_path).current_article("A-1") == "NEW01N"


def test_catalog_overlapping_periods_fail(tmp_path):
    write_catalog(tmp_path / "c.xlsx", prices=[
        ("NEW01N", dt.datetime(2025, 1, 1), dt.datetime(2025, 7, 1), 1, 1),
        ("NEW01N", dt.datetime(2025, 7, 1), None, 1, 1),
    ])
    with pytest.raises(DataFormatError, match="пересекаются"):
        catalog.load(tmp_path)


def test_dedup_keeps_latest_export(data_dir):
    raw = crm.load_raw(data_dir)
    clean = crm.deduplicate(raw)
    assert len(raw) == 4
    assert sorted(zip(clean[crm.ORDER], clean[crm.LINE])) == [(7, 1), (7, 2), (8, 1)]
    line = clean[(clean[crm.ORDER] == 7) & (clean[crm.LINE] == 1)].iloc[0]
    assert line["Статус"] == "PAID"  # версия от 01.01.2030, хотя в файле она выше версии от 01.12.2029


def test_normalize(data_dir):
    df = crm.load_clean(data_dir, catalog.load(data_dir)).set_index([crm.ORDER, crm.LINE])

    first = df.loc[(7, 1)]
    assert first[crm.CREATED] == D(2030, 1, 10)
    assert first[crm.MANAGER] == "Ирина Зайцева"
    assert first[crm.SOURCE] == "Instagram"
    assert first[crm.STATUS] == "Оплачен"
    assert first[crm.ARTICLE] == "NEW01N"            # старый артикул переведён в новый
    assert first[crm.DISCOUNT] == 15_000              # 10% от 150 000
    assert first[crm.UNIT_NET] == 135_000
    assert first[crm.MIN_PRICE] == 110_000            # период 2026 года

    second = df.loc[(7, 2)]
    assert second[crm.LINE_GROSS] == 60_000
    assert second[crm.DISCOUNT] == 5_000              # рубли на всю строку, не на единицу
    assert second[crm.UNIT_NET] == 27_500

    cancelled = df.loc[(8, 1)]
    assert cancelled[crm.CREATED] == D(2025, 1, 10)   # серийный номер Excel
    assert cancelled[crm.STATUS] == "Отменён"
    assert cancelled[crm.UNIT_PRICE] == 98_000
    assert cancelled[crm.CLIENT] == 90002


def test_unknown_status_and_source_only_warn(tmp_path, capsys):
    write_catalog(tmp_path / "c.xlsx")
    write_crm(tmp_path / "01_crm.csv", [
        "A-9;1;2026-01-10;CL-1;Дарья;ВКонтакте;KEEP-01;1;50000;руб;;Частично оплачен;;2030-01-01 09:00",
        "A-9;2;2026-01-10;CL-1;Дарья;ВКонтакте;KEEP-01;1;50000;руб;;Частично оплачен;;2030-01-01 09:00",
    ])
    df = crm.load_clean(tmp_path, catalog.load(tmp_path))
    assert list(df[crm.STATUS]) == ["В работе", "В работе"]
    assert list(df[crm.SOURCE]) == ["ВКонтакте", "ВКонтакте"]
    err = capsys.readouterr().err
    assert err.count("Частично оплачен") == 1  # одно предупреждение на написание
    assert "(2 стр.)" in err and "ВКонтакте" in err


@pytest.mark.parametrize("bad_row, message", [
    ("A-9;1;2026-01-10;CL-1;Иван;IG;KEEP-01;1;50000;руб;;PAID;;2030-01-01 09:00", "менеджер"),
    ("A-9;1;2026-01-10;CL-1;Дарья;IG;NOPE-01;1;50000;руб;;PAID;;2030-01-01 09:00", "каталоге"),
    ("A-9;1;2026-01-10;CL-1;Дарья;IG;KEEP-01;1;50000;USD;;PAID;;2030-01-01 09:00", "валюты"),
    ("A-9;1;2026-01-10;CL-1;Дарья;IG;KEEP-01;1;1,600;руб;;PAID;;2030-01-01 09:00", "суммы"),
    ("A-9;1;вчера;CL-1;Дарья;IG;KEEP-01;1;50000;руб;;PAID;;2030-01-01 09:00", "даты"),
    ("A-9;1;2024-01-10;CL-1;Дарья;IG;KEEP-01;1;50000;руб;;PAID;;2030-01-01 09:00", "периодов цены"),
    ("Б-9;1;2026-01-10;CL-1;Дарья;IG;KEEP-01;1;50000;руб;;PAID;;2030-01-01 09:00", "номер заказа"),
])
def test_unknown_format_fails(tmp_path, bad_row, message):
    write_catalog(tmp_path / "c.xlsx")
    write_crm(tmp_path / "01_crm.csv", [bad_row])
    with pytest.raises(DataFormatError, match=message):
        crm.load_clean(tmp_path, catalog.load(tmp_path))


def test_cp1251_crm(tmp_path):
    write_catalog(tmp_path / "c.xlsx")
    write_crm(tmp_path / "01_crm.csv",
              ["A-1;1;2026-01-10;CL-1;Дарья;IG;KEEP-01;1;50000;руб;;Оплачен;;2030-01-01 09:00"],
              encoding="cp1251")
    df = crm.load_clean(tmp_path, catalog.load(tmp_path))
    assert df.iloc[0][crm.MANAGER] == "Дарья Белкина"
