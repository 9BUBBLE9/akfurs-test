"""Пересчёт answers.json из сырых файлов.

Запуск:  python solve.py data -o answers.json
(без -o JSON печатается в stdout в UTF-8)
"""
import argparse
import json
import sys

from akfurs import catalog, crm, q1

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

    answers = dict.fromkeys(ANSWER_KEYS)
    answers.update(q1.solve(orders))
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
