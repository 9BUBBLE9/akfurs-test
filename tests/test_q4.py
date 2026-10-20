import zipfile

import pytest

from akfurs import chats, q4
from akfurs.money_text import find_amounts
from akfurs.parsing import DataFormatError


@pytest.mark.parametrize("text, expected", [
    ("Итого за модель: 61 000 ₽.", [61_000]),
    ("Полная стоимость 2,615 млн.", [2_615_000]),
    ("Полная стоимость 128 тыс..", [128_000]),
    ("Со скидкой — 2437 тыс., дешевле не получится", [2_437_000]),
    ("Эта модель — 412.000 руб.", [412_000]),
    ("Со скидкой — 2.183.000 руб, дешевле не получится", [2_183_000]),
    ("Могу уступить до 250к", [250_000]),
    ("Со скидкой — два миллиона триста тысяч рублей", [2_300_000]),
    ("Итого за модель: семьсот двадцать три тысячи рублей.", [723_000]),
    ("Полная стоимость девятьсот тысяч рублей.", [900_000]),
    ("Стоимость — сто тридцать две тысячи", [132_000]),
    # не суммы
    ("Можно разбить оплату на 3-4 взноса.", []),
    ("Внесите аванс 40%, остаток при выдаче.", []),
    ("Открыты каждый день с 11 до 20.", []),
    ("Послезавтра в 16:30 подойдёт?", []),
    ("Приходите к 5 к нам в шоурум", []),
    ("Подождите одну минуту", []),
])
def test_find_amounts(text, expected):
    assert find_amounts(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Приглашаю вас примерить модель лично — какой день подходит?", True),
    ("Сможете подъехать в эту пятницу?", True),
    ("Приезжайте посмотреть модель вживую!", True),
    ("Могу записать вас на просмотр в шоуруме.", True),
    ("Ждём вас в субботу!", True),
    ("Шоурум расположен в центре, открыт каждый день с 11 до 20.", False),
    ("Каждое изделие отшиваем по индивидуальным меркам.", False),
    ("Какой у вас размер?", False),
])
def test_is_invite(text, expected):
    assert q4.is_invite(text) is expected


def make_chat(*lines, chat_id="C0001"):
    head = f"Чат {chat_id} | клиент cl90001 | заказ A-00001 | менеджер Дарья"
    return chats.parse_chat(f"{chat_id}.txt", "\n".join([head, *lines]))


def test_parse_chat_multiline_and_order(capsys):
    chat = make_chat(
        "[01.02.2025 10:05] Менеджер: Стоимость —",
        "  120 000 ₽",                                  # продолжение сообщения
        "[01.02.2025 10:00] Клиент: Сколько стоит?",    # не по порядку
    )
    assert [m.speaker for m in chat.messages] == [chats.CLIENT, chats.MANAGER]
    assert chat.messages[1].text == "Стоимость —\n120 000 ₽"
    assert "не по порядку" in capsys.readouterr().err


def test_parse_chat_unknown_speaker():
    with pytest.raises(DataFormatError, match="автор"):
        make_chat("[01.02.2025 10:00] Бот: Здравствуйте")


CASES = {
    "invite_then_price": (["[01.02.2025 10:00] Менеджер: Приглашаю вас в шоурум!",
                           "[01.02.2025 10:01] Менеджер: Стоимость — 120 000 ₽."], True),
    "price_then_invite": (["[01.02.2025 10:00] Менеджер: Стоимость — сто двадцать тысяч рублей.",
                           "[01.02.2025 10:01] Менеджер: Сможете подъехать в пятницу?"], False),
    "invite_no_price": (["[01.02.2025 10:00] Менеджер: Приезжайте посмотреть вживую!",
                         "[01.02.2025 10:01] Клиент: Сначала скажите цену, пожалуйста."], True),
    "same_message": (["[01.02.2025 10:00] Менеджер: Цена 120 тыс., приглашаю вас в шоурум."], False),
    "no_invite": (["[01.02.2025 10:00] Менеджер: Стоимость — 120 000 ₽."], False),
    # сумму называет клиент, «загляну» говорит клиент — это не цена и не приглашение
    "client_sum_and_visit": (["[01.02.2025 10:00] Клиент: Нашла за 650 тыс., загляну в пятницу",
                              "[01.02.2025 10:01] Менеджер: Шоурум в центре, открыт с 11 до 20.",
                              "[01.02.2025 10:02] Менеджер: Приглашаю вас в шоурум!",
                              "[01.02.2025 10:03] Менеджер: Стоимость — 650 000 ₽."], True),
    "number_not_price": (["[01.02.2025 10:00] Менеджер: Можно разбить оплату на 3-4 взноса.",
                          "[01.02.2025 10:01] Менеджер: Получится приехать на просмотр? Послезавтра в 16:30.",
                          "[01.02.2025 10:02] Менеджер: Итого за модель: 2,4 млн."], True),
}


@pytest.mark.parametrize("name", CASES)
def test_judge(name):
    lines, expected = CASES[name]
    assert q4.judge(make_chat(*lines)).invite_before_price is expected


def test_solve_from_zip(tmp_path):
    with zipfile.ZipFile(tmp_path / "04_client_chats.zip", "w") as zf:
        for chat_id, (lines, _) in zip(["C0002", "C0001"], [CASES["invite_no_price"],
                                                            CASES["price_then_invite"]]):
            head = f"Чат {chat_id} | клиент cl1 | заказ A-1 | менеджер Дарья"
            zf.writestr(f"chats/{chat_id}.txt", "\n".join([head, *lines]))
    assert q4.solve(chats.load(tmp_path)) == {"q4_chats_meeting_before_price": ["C0002"]}
