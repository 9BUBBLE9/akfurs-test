"""Словари написаний. Ключи — в нормализованном виде (см. parsing.norm_key).

Если в новой выгрузке встретится незнакомое написание, код упадёт с ошибкой
и подскажет, какое значение добавить сюда.
"""

STATUS_PAID = "Оплачен"
STATUS_CANCELLED = "Отменён"
STATUS_REFUND = "Возврат"
STATUS_IN_PROGRESS = "В работе"

STATUSES = {
    "оплачен": STATUS_PAID,
    "оплачено": STATUS_PAID,
    "paid": STATUS_PAID,
    "отменен": STATUS_CANCELLED,
    "отменено": STATUS_CANCELLED,
    "cancelled": STATUS_CANCELLED,
    "canceled": STATUS_CANCELLED,
    "возврат": STATUS_REFUND,
    "refund": STATUS_REFUND,
    # всё, что не первые три, по ТЗ — «В работе»; перечисляем явно,
    # чтобы незнакомый статус не попал сюда молча
    "в работе": STATUS_IN_PROGRESS,
    "new": STATUS_IN_PROGRESS,
    "новый": STATUS_IN_PROGRESS,
    "ждем оплату": STATUS_IN_PROGRESS,
}

CURRENCIES = {
    "rub": "RUB",
    "rur": "RUB",
    "руб": "RUB",
    "руб.": "RUB",
    "₽": "RUB",
}

SOURCES = {
    "instagram": "Instagram",
    "insta": "Instagram",
    "ig": "Instagram",
    "инстаграм": "Instagram",
    "telegram": "Telegram",
    "телеграм": "Telegram",
    "tg": "Telegram",
    "рекомендация": "Рекомендация",
    "реком.": "Рекомендация",
    "сарафан": "Рекомендация",
    "сайт": "Сайт",
    "site": "Сайт",
    "заявка с сайта": "Сайт",
    "яндекс карты": "Яндекс Карты",
    "я.карты": "Яндекс Карты",
    "yandex maps": "Яндекс Карты",
}

# первые три буквы названия месяца (родительный падеж, сокращения)
MONTHS = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5,
    "июн": 6, "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}
