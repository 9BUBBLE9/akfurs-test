"""Q2. Сверка заказов CRM с поступлениями по выписке."""
from . import bank, crm
from .dictionaries import STATUS_PAID, TYPE_INCOMING
from .io_utils import warn


def match_payments(payments, existing_orders):
    """Номер заказа для каждой операции или None (неопознанная).

    Платёж относится к заказу, если в назначении есть номер существующего заказа.
    Если существующих номеров несколько — платёж неоднозначный и считается неопознанным.
    """
    matched = []
    for row, purpose, candidates in zip(payments[bank.SOURCE_ROW], payments[bank.COL_PURPOSE],
                                        payments[bank.ORDER_CANDIDATES]):
        hits = [n for n in candidates if n in existing_orders]
        if len(hits) > 1:
            warn(f"Выписка, строка {row}: несколько заказов {hits} в '{purpose}' — неопознанный")
        matched.append(hits[0] if len(hits) == 1 else None)
    return matched


def solve(orders, payments):
    existing = set(orders[crm.ORDER])
    incoming = payments[payments[bank.TYPE] == TYPE_INCOMING].copy()
    incoming["order"] = match_payments(incoming, existing)

    # статус заказа — статус его строк (совпадение по строкам проверяется в crm)
    order_status = orders.sort_values(crm.LINE).groupby(crm.ORDER)[crm.STATUS].first()
    paid_orders = set(order_status[order_status == STATUS_PAID].index)
    with_payment = set(incoming["order"].dropna().astype(int))

    unidentified = incoming[incoming["order"].isna()]
    total = round(float(unidentified[bank.AMOUNT].sum()), 2)
    return {
        "q2a_paid_orders_without_payment": sorted(paid_orders - with_payment),
        "q2b_unidentified_payments_count": int(len(unidentified)),
        "q2b_unidentified_payments_sum_rub": int(total) if total.is_integer() else total,
    }
