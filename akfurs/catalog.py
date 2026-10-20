"""Справочник из Excel: каталог, переименования артикулов, история цен, менеджеры."""
import datetime as dt
from dataclasses import dataclass

import pandas as pd

from .io_utils import find_file, read_excel_table, require_columns
from .parsing import DataFormatError, norm_key, parse_article, parse_date, parse_money

CATALOG_PATTERN = "*.xlsx"

SHEET_CATALOG = "Каталог"
SHEET_RENAMES = "Переименования"
SHEET_PRICES = "Прайс_история"
SHEET_MANAGERS = "Менеджеры"

COL_ARTICLE = "Артикул"
COL_OLD = "Старый артикул"
COL_NEW = "Новый артикул"
COL_FROM = "Действует с"
COL_TO = "Действует по"
COL_REC = "Рекомендованная цена, ₽"
COL_MIN = "Минимально допустимая цена, ₽"
COL_CANON = "Каноническое имя"
COL_ALIASES = "Варианты написания в CRM"


def to_date(value):
    """Ячейка Excel -> date или None для пустой."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, (dt.datetime, pd.Timestamp)):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return parse_date(value)


def to_money(value):
    if isinstance(value, (int, float)) and not pd.isna(value):
        return float(value)
    return parse_money(value)


@dataclass
class Catalog:
    articles: set
    renames: dict          # старый артикул -> актуальный (цепочки уже развёрнуты)
    prices: pd.DataFrame   # article, date_from, date_to (None = бессрочно), rec_price, min_price
    managers: dict         # norm_key(написание) -> каноническое имя

    def current_article(self, article):
        return self.renames.get(article, article)

    def canonical_manager(self, name):
        key = norm_key(name)
        if key not in self.managers:
            raise DataFormatError(f"менеджер '{name}' не найден в справочнике '{SHEET_MANAGERS}'")
        return self.managers[key]

    def min_price(self, article, on_date):
        """Минимальная цена актуального артикула на дату; ровно один период, иначе ошибка."""
        rows = self.prices[self.prices.article == article]
        hit = [r for r in rows.itertuples()
               if r.date_from <= on_date and (pd.isna(r.date_to) or r.date_to >= on_date)]
        if len(hit) != 1:
            raise DataFormatError(f"для артикула {article} на {on_date} найдено "
                                  f"{len(hit)} периодов цены в '{SHEET_PRICES}'")
        return float(hit[0].min_price)


def _resolve_renames(pairs):
    """old -> new с разворотом цепочек A->B->C; цикл или два разных new у одного old — ошибка."""
    direct = {}
    for old, new in pairs:
        if direct.get(old, new) != new:
            raise DataFormatError(f"артикул {old} переименован в разные: {direct[old]} и {new}")
        direct[old] = new
    resolved = {}
    for old in direct:
        seen, cur = {old}, direct[old]
        while cur in direct:
            if cur in seen:
                raise DataFormatError(f"цикл в переименованиях артикулов: {old}")
            seen.add(cur)
            cur = direct[cur]
        resolved[old] = cur
    return resolved


def _check_price_periods(prices):
    for article, grp in prices.sort_values("date_from").groupby("article"):
        rows = list(grp.itertuples())
        for prev, cur in zip(rows, rows[1:]):
            if pd.isna(prev.date_to) or prev.date_to >= cur.date_from:
                raise DataFormatError(f"пересекаются периоды цены у {article}: "
                                      f"{prev.date_from}–{prev.date_to} и {cur.date_from}")


def load(data_dir):
    path = find_file(data_dir, CATALOG_PATTERN)

    cat = read_excel_table(path, SHEET_CATALOG, COL_ARTICLE)
    require_columns(cat, [COL_ARTICLE], SHEET_CATALOG)
    articles = {parse_article(a) for a in cat[COL_ARTICLE]}

    ren = read_excel_table(path, SHEET_RENAMES, COL_OLD)
    require_columns(ren, [COL_OLD, COL_NEW], SHEET_RENAMES)
    renames = _resolve_renames((parse_article(o), parse_article(n))
                               for o, n in zip(ren[COL_OLD], ren[COL_NEW]))

    pr = read_excel_table(path, SHEET_PRICES, COL_ARTICLE)
    require_columns(pr, [COL_ARTICLE, COL_FROM, COL_TO, COL_REC, COL_MIN], SHEET_PRICES)
    prices = pd.DataFrame({
        "article": [parse_article(a) for a in pr[COL_ARTICLE]],
        "date_from": [to_date(v) for v in pr[COL_FROM]],
        "date_to": [to_date(v) for v in pr[COL_TO]],
        "rec_price": [to_money(v) for v in pr[COL_REC]],
        "min_price": [to_money(v) for v in pr[COL_MIN]],
    })
    if any(d is None for d in prices.date_from):
        raise DataFormatError(f"'{SHEET_PRICES}': есть строки без даты '{COL_FROM}'")
    # в истории цен должны быть актуальные артикулы, а не старые
    stale = set(prices.article) & set(renames)
    if stale:
        raise DataFormatError(f"'{SHEET_PRICES}' содержит старые артикулы {sorted(stale)}")
    _check_price_periods(prices)

    mg = read_excel_table(path, SHEET_MANAGERS, COL_CANON)
    require_columns(mg, [COL_CANON, COL_ALIASES], SHEET_MANAGERS)
    managers = {}
    for canon, aliases in zip(mg[COL_CANON], mg[COL_ALIASES]):
        canon = str(canon).strip()
        for alias in [canon, *str(aliases).split("|")]:
            key = norm_key(alias)
            if key in managers and managers[key] != canon:
                raise DataFormatError(f"написание '{alias}' относится к двум менеджерам: "
                                      f"{managers[key]} и {canon}")
            managers[key] = canon

    return Catalog(articles=articles, renames=renames, prices=prices, managers=managers)
