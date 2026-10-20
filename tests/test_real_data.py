"""Инварианты на настоящих выгрузках (data/ не в git — без неё тесты пропускаются)."""
from pathlib import Path

import pytest

from akfurs import catalog, crm

DATA = Path(__file__).resolve().parents[1] / "data"
pytestmark = pytest.mark.skipif(not any(DATA.glob("*crm*.csv")), reason="нет папки data/")


@pytest.fixture(scope="module")
def orders():
    return crm.load_clean(DATA, catalog.load(DATA))


def test_keys_unique(orders):
    assert not orders.duplicated([crm.ORDER, crm.LINE]).any()


def test_every_line_has_min_price(orders):
    assert orders[crm.MIN_PRICE].notna().all()
    assert (orders[crm.MIN_PRICE] > 0).all()


def test_all_fields_normalized(orders):
    for col in [crm.CREATED, crm.CLIENT, crm.MANAGER, crm.SOURCE, crm.STATUS,
                crm.CURRENCY, crm.ARTICLE, crm.QTY, crm.UNIT_PRICE, crm.DISCOUNT]:
        assert orders[col].notna().all(), col
    assert set(orders[crm.STATUS]) <= {"Оплачен", "Отменён", "Возврат", "В работе"}
    assert (orders[crm.UNIT_NET] > 0).all()
