"""Q1. Сколько уникальных заказов и строк заказов после очистки."""
from .crm import ORDER


def solve(crm):
    return {
        "q1_unique_orders": int(crm[ORDER].nunique()),
        "q1_unique_order_lines": int(len(crm)),
    }
