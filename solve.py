"""Пересчёт answers.json из сырых файлов.

Запуск:  python solve.py data -o answers.json
(без -o JSON печатается в stdout в UTF-8)
"""
import argparse
import json
import sys

from akfurs import bank, catalog, crm, q1, q2, q3

RUN_COMMAND = "python solve.py data -o answers.json"

NOTES = [
    "Q1: номер заказа — число после необязательного префикса A/А (лат./кир., любой регистр) "
    "и дефиса, ведущие нули и пробелы игнорируются. Дубли пары «заказ + № строки» схлопываются "
    "до версии с самым поздним «Выгружено»; при равном времени берётся строка ниже в файле.",
    "Нормализация CRM: даты вида NN/NN/YYYY читаются как ДД/ММ (порядок определяется по данным: "
    "где-то первое число > 12), пятизначные числа — серийные даты Excel. Скидка «N%» считается от "
    "Цена × Кол-во, скидка числом — рубли на всю строку; цена за единицу после скидки = "
    "(Цена × Кол-во − скидка) / Кол-во. Старые артикулы всегда переводятся в новые по листу "
    "«Переименования», независимо от даты перехода (старый код встречается и после неё). "
    "Статусы сопоставляются по словарю; NEW, «Ждём оплату» и любой незнакомый статус — "
    "«В работе» (незнакомый — с предупреждением). Незнакомый формат даты, суммы, количества, "
    "скидки, валюты, артикула, менеджера или номера заказа останавливает расчёт с ошибкой.",
    "Q2: учитываются только операции «Поступление»; списания (возвраты клиентам) не считаются ни "
    "оплатой, ни неопознанными поступлениями. Номер заказа в назначении — код с буквой A/А "
    "(A-00075, А-75, A75) или число после слов «заказ», «зак.», «счёт/счету №»; номер счёта "
    "считается номером заказа (суммы таких платежей распределены так же, как у платежей с явным "
    "номером заказа, и ни один не пришёл раньше создания заказа). Прочие числа (телефоны, даты "
    "счетов) игнорируются. Номер должен существовать в CRM (любой статус, включая «Отменён»); "
    "несуществующий номер (A-09999) или его отсутствие — платёж неопознанный. Частичная оплата "
    "(предоплата) тоже считается поступлением по заказу. Статус заказа — статус его строк.",
    "Q3: исключены только строки «Отменён» («Возврат» и «В работе» учитываются). Цена за единицу "
    "после скидки = (Цена × Кол-во − скидка) / Кол-во, округление до копеек; нарушение — строго "
    "ниже минимальной цены (ровно на минимуме — не нарушение). Минимальная цена берётся из периода "
    "«Прайс_история», в который попадает дата создания заказа (границы включительно); старый "
    "артикул всегда заменяется новым по «Переименованиям». В разбивке указаны все канонические "
    "менеджеры из справочника, включая тех, у кого нарушений нет (0).",
]

# порядок ключей — как в answers_template.json
ANSWER_KEYS = [
    "q1_unique_orders",
    "q1_unique_order_lines",
    "q2a_paid_orders_without_payment",
    "q2b_unidentified_payments_count",
    "q2b_unidentified_payments_sum_rub",
    "q3_price_violation_lines_total",
    "q3_price_violation_lines_by_manager",
    "q4_chats_meeting_before_price",
    "run_command",
    "notes",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", help="папка с сырыми файлами")
    parser.add_argument("-o", "--out", help="куда записать answers.json (по умолчанию stdout)")
    args = parser.parse_args()

    reference = catalog.load(args.data_dir)
    orders = crm.load_clean(args.data_dir, reference)
    payments = bank.load(args.data_dir)

    answers = dict.fromkeys(ANSWER_KEYS)
    answers.update(q1.solve(orders))
    answers.update(q2.solve(orders, payments))
    answers.update(q3.solve(orders, reference.manager_names))
    answers["run_command"] = RUN_COMMAND
    answers["notes"] = " ".join(NOTES)

    text = json.dumps(answers, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)


if __name__ == "__main__":
    main()
