from akfurs import catalog, crm, q3
from conftest import write_catalog, write_crm

# мин. цена: NEW01N — 100 000 (2025) / 110 000 (2026), KEEP-01 — 50 000
ROWS = [
    # нарушение: старый артикул после переименования, 2026 год, 105 000 < 110 000
    "A-1;1;2026-02-01;CL-1;darya.b;IG;OLD-01;1;105 000;руб;;PAID;;2030-01-01 09:00",
    # та же цена в 2025 году — не нарушение (минимум 100 000)
    "A-2;1;2025-12-31;CL-1;darya.b;IG;OLD-01;1;105 000;руб;;PAID;;2030-01-01 09:00",
    # ровно на минимуме после скидки 10% — не нарушение
    "A-3;1;2026-02-01;CL-1;Дарья;IG;KEEP-01;1;55 555,56;руб;10%;PAID;;2030-01-01 09:00",
    # ниже минимума только из-за скидки в рублях на строку: (2×52 000 − 5 000)/2 = 49 500
    "A-4;1;2026-02-01;CL-1;Irina Z;IG;KEEP-01;2;52 000;руб;5 000;Возврат;;2030-01-01 09:00",
    # ниже минимума, но заказ отменён — не считается
    "A-5;1;2026-02-01;CL-1;Irina Z;IG;KEEP-01;1;10 000;руб;;отменен;;2030-01-01 09:00",
    # незнакомый статус -> «В работе», считается
    "A-6;1;2026-02-01;CL-1;Дарья;IG;KEEP-01;1;40 000;руб;;Ждём доплату;;2030-01-01 09:00",
]


def test_q3(tmp_path):
    write_catalog(tmp_path / "c.xlsx")
    write_crm(tmp_path / "01_crm.csv", ROWS)
    ref = catalog.load(tmp_path)
    orders = crm.load_clean(tmp_path, ref)

    assert sorted(q3.violations(orders)[crm.ORDER]) == [1, 4, 6]
    assert q3.solve(orders) == {
        "q3_price_violation_lines_total": 3,
        "q3_price_violation_lines_by_manager": {"Дарья Белкина": 2, "Ирина Зайцева": 1},
    }


def test_q3_no_violations(tmp_path):
    write_catalog(tmp_path / "c.xlsx")
    write_crm(tmp_path / "01_crm.csv", ROWS[1:3])
    result = q3.solve(crm.load_clean(tmp_path, catalog.load(tmp_path)))
    assert result == {"q3_price_violation_lines_total": 0, "q3_price_violation_lines_by_manager": {}}
