"""Выгрузка CRM: нормализация ключа строки и удаление дублей."""
import pandas as pd

from .io_utils import find_file, parse_order_number, read_csv_text, warn

CRM_PATTERN = "*crm*.csv"

COL_ORDER = "Номер заказа"
COL_LINE = "№ строки"
COL_EXPORTED = "Выгружено"

# служебные колонки, которые добавляем к сырым
ORDER = "order_no"
LINE = "line_no"
EXPORTED = "exported_at"
SOURCE_ROW = "source_row"


def load_raw(data_dir):
    """Сырые строки CRM + нормализованные номер заказа, № строки, время выгрузки."""
    df = read_csv_text(find_file(data_dir, CRM_PATTERN), header_marker=COL_ORDER)
    df[SOURCE_ROW] = df.index + 2  # номер строки в файле (с учётом заголовка)
    df[ORDER] = df[COL_ORDER].map(parse_order_number)
    df[LINE] = pd.to_numeric(df[COL_LINE].str.strip(), errors="coerce")
    df[EXPORTED] = pd.to_datetime(df[COL_EXPORTED].str.strip(), errors="coerce")

    bad_key = df[ORDER].isna() | df[LINE].isna()
    for _, r in df[bad_key].iterrows():
        warn(f"CRM, строка {r[SOURCE_ROW]}: не распознан ключ "
             f"'{r[COL_ORDER]}' / '{r[COL_LINE]}' — строка пропущена")
    for _, r in df[~bad_key & df[EXPORTED].isna()].iterrows():
        warn(f"CRM, строка {r[SOURCE_ROW]}: не распознано '{COL_EXPORTED}'='{r[COL_EXPORTED]}'")

    df = df[~bad_key].copy()
    df[ORDER] = df[ORDER].astype(int)
    df[LINE] = df[LINE].astype(int)
    return df


def deduplicate(raw):
    """Одна строка на пару (заказ, № строки) — с самым поздним «Выгружено».

    При равном времени выгрузки побеждает строка, стоящая ниже в файле;
    если такие строки различаются по содержимому, выводим предупреждение.
    """
    ordered = raw.sort_values([EXPORTED, SOURCE_ROW], na_position="first", kind="stable")
    clean = ordered.drop_duplicates([ORDER, LINE], keep="last")

    content_cols = [c for c in raw.columns if c not in (COL_ORDER, SOURCE_ROW)]
    latest = ordered.groupby([ORDER, LINE])[EXPORTED].transform("max")
    tied = ordered[ordered[EXPORTED] == latest]
    for key, grp in tied.groupby([ORDER, LINE]):
        if len(grp.drop_duplicates(content_cols)) > 1:
            warn(f"CRM, заказ {key[0]} строка {key[1]}: разные версии с одинаковым "
                 f"'{COL_EXPORTED}', взята последняя в файле (строка {grp[SOURCE_ROW].max()})")

    return clean.sort_values([ORDER, LINE]).reset_index(drop=True)


def load_clean(data_dir):
    return deduplicate(load_raw(data_dir))
