"""Выгрузка CRM: ключи строк, удаление дублей, нормализация полей."""
from .io_utils import find_file, read_csv_text, require_columns, warn
from .parsing import (
    DataFormatError, clean_spaces, infer_slash_order, lookup, norm_key, parse_article,
    parse_client_id, parse_date, parse_datetime, parse_discount, parse_line_number, parse_money,
    parse_order_number, parse_quantity,
)
from .dictionaries import CURRENCIES, SOURCES, STATUS_IN_PROGRESS, STATUSES

CRM_PATTERN = "*crm*.csv"

COL_ORDER = "Номер заказа"
COL_LINE = "№ строки"
COL_CREATED = "Дата создания"
COL_CLIENT = "Клиент"
COL_MANAGER = "Менеджер"
COL_SOURCE = "Источник"
COL_ARTICLE = "Артикул"
COL_QTY = "Кол-во"
COL_PRICE = "Цена за ед."
COL_CURRENCY = "Валюта"
COL_DISCOUNT = "Скидка"
COL_STATUS = "Статус"
COL_COMMENT = "Комментарий"
COL_EXPORTED = "Выгружено"
REQUIRED = [COL_ORDER, COL_LINE, COL_CREATED, COL_CLIENT, COL_MANAGER, COL_SOURCE, COL_ARTICLE,
            COL_QTY, COL_PRICE, COL_CURRENCY, COL_DISCOUNT, COL_STATUS, COL_COMMENT, COL_EXPORTED]

# служебные колонки, которые добавляем к сырым
SOURCE_ROW = "source_row"
ORDER = "order_no"
LINE = "line_no"
EXPORTED = "exported_at"
CREATED = "created"
CLIENT = "client_id"
MANAGER = "manager"
SOURCE = "source"
ARTICLE = "article"          # актуальный артикул (после переименований)
QTY = "qty"
UNIT_PRICE = "unit_price"
CURRENCY = "currency"
DISCOUNT = "discount_rub"    # скидка в рублях на всю строку
LINE_GROSS = "line_gross"    # Цена × Кол-во
LINE_NET = "line_net"        # после скидки
UNIT_NET = "unit_net"        # цена за единицу после скидки
STATUS = "status"
COMMENT = "comment"
MIN_PRICE = "min_price"      # минимально допустимая цена на дату создания

MAX_REPORTED_ERRORS = 30


class _Errors:
    """Копит ошибки разбора по всем строкам, чтобы показать их разом."""

    def __init__(self):
        self.items = []

    def apply(self, df, label, func, *cols):
        out = []
        for row, *values in zip(df[SOURCE_ROW], *(df[c] for c in cols)):
            try:
                out.append(func(*values))
            except DataFormatError as e:
                self.items.append(f"строка {row}, {label}: {e}")
                out.append(None)
        return out

    def raise_if_any(self, source):
        if self.items:
            shown = "\n  ".join(self.items[:MAX_REPORTED_ERRORS])
            more = len(self.items) - MAX_REPORTED_ERRORS
            tail = f"\n  ... и ещё {more}" if more > 0 else ""
            raise DataFormatError(f"{source}: {len(self.items)} ошибок формата:\n  {shown}{tail}")


def load_raw(data_dir):
    """Сырые строки CRM + разобранные номер заказа, № строки и время выгрузки."""
    df = read_csv_text(find_file(data_dir, CRM_PATTERN), header_marker=COL_ORDER)
    require_columns(df, REQUIRED, "CRM")
    df[SOURCE_ROW] = df.index + 2  # номер строки в файле (с учётом заголовка)

    errors = _Errors()
    df[ORDER] = errors.apply(df, COL_ORDER, parse_order_number, COL_ORDER)
    df[LINE] = errors.apply(df, COL_LINE, parse_line_number, COL_LINE)
    df[EXPORTED] = errors.apply(df, COL_EXPORTED, parse_datetime, COL_EXPORTED)
    errors.raise_if_any("CRM")
    return df


def deduplicate(raw):
    """Одна строка на пару (заказ, № строки) — с самым поздним «Выгружено».

    При равном времени выгрузки побеждает строка, стоящая ниже в файле;
    если такие строки различаются по содержимому, выводим предупреждение.
    """
    ordered = raw.sort_values([EXPORTED, SOURCE_ROW], kind="stable")
    clean = ordered.drop_duplicates([ORDER, LINE], keep="last")

    content_cols = [c for c in raw.columns if c not in (COL_ORDER, SOURCE_ROW)]
    latest = ordered.groupby([ORDER, LINE])[EXPORTED].transform("max")
    tied = ordered[ordered[EXPORTED] == latest]
    for key, grp in tied.groupby([ORDER, LINE]):
        if len(grp.drop_duplicates(content_cols)) > 1:
            warn(f"CRM, заказ {key[0]} строка {key[1]}: разные версии с одинаковым "
                 f"'{COL_EXPORTED}', взята последняя в файле (строка {grp[SOURCE_ROW].max()})")

    return clean.sort_values([ORDER, LINE]).reset_index(drop=True)


def normalize(df, catalog):
    """Разбирает все поля строк заказа.

    Незнакомый формат — DataFormatError; исключения — статус и источник (только предупреждение).
    """
    df = df.copy()
    errors = _Errors()
    slash_order = infer_slash_order(df[COL_CREATED])

    df[CREATED] = errors.apply(df, COL_CREATED, lambda v: parse_date(v, slash_order), COL_CREATED)
    df[CLIENT] = errors.apply(df, COL_CLIENT, parse_client_id, COL_CLIENT)
    df[MANAGER] = errors.apply(df, COL_MANAGER, catalog.canonical_manager, COL_MANAGER)
    # по ТЗ всё, что не Оплачен/Отменён/Возврат, — «В работе»; источник в ответах не участвует
    df[STATUS] = _map_with_warning(df[COL_STATUS], STATUSES, lambda v: STATUS_IN_PROGRESS,
                                   COL_STATUS, f"считается «{STATUS_IN_PROGRESS}»")
    df[SOURCE] = _map_with_warning(df[COL_SOURCE], SOURCES, clean_spaces,
                                   COL_SOURCE, "оставлен как есть")
    df[CURRENCY] = errors.apply(df, COL_CURRENCY, lambda v: lookup(v, CURRENCIES, "валюты"),
                                COL_CURRENCY)
    df[QTY] = errors.apply(df, COL_QTY, parse_quantity, COL_QTY)
    df[UNIT_PRICE] = errors.apply(df, COL_PRICE, parse_money, COL_PRICE)
    df[COMMENT] = df[COL_COMMENT].map(clean_spaces)

    def current_article(raw):
        article = catalog.current_article(parse_article(raw))
        if article not in catalog.articles:
            raise DataFormatError(f"артикула '{raw}' (актуальный {article}) нет в каталоге")
        return article
    df[ARTICLE] = errors.apply(df, COL_ARTICLE, current_article, COL_ARTICLE)
    errors.raise_if_any("CRM")

    df[LINE_GROSS] = (df[UNIT_PRICE] * df[QTY]).round(2)
    df[DISCOUNT] = errors.apply(df, COL_DISCOUNT, parse_discount, COL_DISCOUNT, LINE_GROSS)
    df[MIN_PRICE] = errors.apply(df, "мин. цена", catalog.min_price, ARTICLE, CREATED)
    errors.raise_if_any("CRM")

    df[LINE_NET] = (df[LINE_GROSS] - df[DISCOUNT]).round(2)
    df[UNIT_NET] = (df[LINE_NET] / df[QTY]).round(2)

    _check_order_consistency(df)
    return df


def _map_with_warning(values, mapping, default, label, action):
    """Значение по словарю; незнакомое -> default(value) и одно предупреждение на написание."""
    keys = values.map(norm_key)
    unknown = values[~keys.isin(mapping.keys())]
    for raw, count in unknown.value_counts().items():
        warn(f"CRM: незнакомое значение '{label}' = '{raw}' ({count} стр.) — {action}; "
             f"при необходимости добавьте '{norm_key(raw)}' в akfurs/dictionaries.py")
    return [mapping[k] if k in mapping else default(v) for k, v in zip(keys, values)]


def _check_order_consistency(df):
    """Поля уровня заказа должны совпадать во всех его строках."""
    for col, label in [(CREATED, COL_CREATED), (CLIENT, COL_CLIENT),
                       (MANAGER, COL_MANAGER), (STATUS, COL_STATUS)]:
        n_values = df.groupby(ORDER)[col].nunique()
        for order in n_values[n_values > 1].index:
            values = sorted(map(str, df.loc[df[ORDER] == order, col].unique()))
            warn(f"CRM, заказ {order}: разные значения '{label}' в строках: {values}")


def load_clean(data_dir, catalog):
    return normalize(deduplicate(load_raw(data_dir)), catalog)
