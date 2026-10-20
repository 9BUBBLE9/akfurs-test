"""Денежные суммы в свободном тексте: цифрами (61 000 ₽, 2,615 млн, 128 тыс.) и прописью.

Сумма — это число с денежной единицей или множителем: ₽, руб., р., тыс., к, млн,
либо числительные прописью со словами «рублей / тысяч / миллионов».
Числа без единицы («3-4 взноса», «40%», «с 11 до 20», «в 16:30») суммой не считаются.
"""
import re

NUMBER = r"\d{1,3}(?:[  .,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
UNIT = r"млн|миллион[а-я]*|тыс[а-я]*|₽|руб[а-я]*|р"
# «к/k» — только слитно (250к), иначе путается с предлогом «к»
DIGIT_MONEY_RE = re.compile(rf"(?<![\d.,])({NUMBER})(?:\s?({UNIT})|([kк]))(?![а-яa-z])\.?",
                            re.IGNORECASE)

SCALE = {"млн": 1_000_000, "миллион": 1_000_000, "тыс": 1_000, "k": 1_000, "к": 1_000}


def _scale(unit):
    unit = unit.lower()
    return next((v for k, v in SCALE.items() if unit.startswith(k)), 1)


def _number(text, scaled):
    """'2 300 000' / '2.183.000' / '75.000' / '2,615' -> float.

    Группы по три цифры через пробел/точку/запятую — разделители тысяч, кроме записи
    с множителем (2,615 млн = 2.615 млн), где запятая/точка — десятичная.
    """
    s = text.replace(" ", " ")
    if scaled and re.fullmatch(r"\d+[.,]\d+", s):
        return float(s.replace(",", "."))
    if re.fullmatch(r"\d{1,3}(?:[ .,]\d{3})+", s):
        return float(re.sub(r"[ .,]", "", s))
    if m := re.fullmatch(r"(\d{1,3}(?:[ .,]\d{3})+)[.,](\d{1,2})", s):
        return float(re.sub(r"[ .,]", "", m[1]) + "." + m[2])
    return float(s.replace(" ", "").replace(",", "."))


# ---------- прописью ----------

UNITS = {
    "ноль": 0, "один": 1, "одна": 1, "одну": 1, "два": 2, "две": 2, "три": 3, "четыре": 4,
    "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14,
    "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
    "девятнадцать": 19, "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
    "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90,
    "сто": 100, "двести": 200, "триста": 300, "четыреста": 400, "пятьсот": 500,
    "шестьсот": 600, "семьсот": 700, "восемьсот": 800, "девятьсот": 900,
}
MULTIPLIERS = {"тысяч": 1_000, "миллион": 1_000_000}
WORD_RE = re.compile(r"[а-яё]+")


def _words_amounts(text):
    """Суммы прописью: последовательность числительных, за которой идут тысячи/миллионы/рубли."""
    amounts, total, current, in_number = [], 0, 0, False
    for word in WORD_RE.findall(text.lower().replace("ё", "е")):
        mult = next((v for k, v in MULTIPLIERS.items() if word.startswith(k)), None)
        if word in UNITS:
            current += UNITS[word]
            in_number = True
        elif mult and in_number:
            total += max(current, 1) * mult
            current = 0
        elif word.startswith("рубл") and in_number:
            amounts.append(total + current)
            total, current, in_number = 0, 0, False
        else:
            if in_number and total:  # «двести тысяч» без слова «рублей»
                amounts.append(total + current)
            total, current, in_number = 0, 0, False
    if in_number and total:
        amounts.append(total + current)
    return amounts


def find_amounts(text):
    """Все денежные суммы в тексте, в рублях."""
    found = []
    for m in DIGIT_MONEY_RE.finditer(text):
        scale = _scale(m[2] or m[3])
        found.append(round(_number(m[1], scaled=scale > 1) * scale, 2))
    return found + _words_amounts(text)
