"""Q3. Строки заказов, проданные ниже минимально допустимой цены."""
from . import crm
from .dictionaries import STATUS_CANCELLED


def violations(orders):
    """Строки (кроме «Отменён»), где цена за единицу после скидки строго ниже минимальной
    на дату создания заказа. Обе цены округлены до копеек, поэтому равенство не нарушение."""
    active = orders[orders[crm.STATUS] != STATUS_CANCELLED]
    return active[active[crm.UNIT_NET] < active[crm.MIN_PRICE]]


def solve(orders):
    """Разбивка только по менеджерам, у которых есть нарушения."""
    bad = violations(orders)
    counts = bad[crm.MANAGER].value_counts()
    by_manager = dict(sorted(((name, int(n)) for name, n in counts.items()),
                             key=lambda kv: (-kv[1], kv[0])))
    return {
        "q3_price_violation_lines_total": int(len(bad)),
        "q3_price_violation_lines_by_manager": by_manager,
    }
