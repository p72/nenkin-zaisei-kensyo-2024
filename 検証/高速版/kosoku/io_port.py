# -*- coding: utf-8 -*-
"""移植版（＝原本）の CSV 形式の読み書き
========================================
高速版は上流が未実装のあいだ移植版の CSV を食い、下流には移植版の列配置で
書く（`compare_option.py` と `compare_keisaihyou.py` が無改造で読めるように）。
177本の完全再現はしない。受け渡し12本 ＋ `01shushi`/`03summary`/`kekka`。

読み手の約束: **位置で添字を切らず、ラベル列を読んで `YEARS.i(label)` で置く**
（`計画.md`「軸の統一」）。年度ラベルは西暦（③④）と西暦−2000（②⑤の一部）が
混じるので、`year_base` を読み手ごとに明示する。

文字コードは原本の出力に UTF-8 と EUC-JP が混じる（仕様書 §12.2）ので
先頭行で見分ける。

フェーズ 0 で置くのは共通の読み手だけ。段階ごとの `from_port_csv` は各
フェーズで足す。
"""
import glob
import os
import re

import numpy as np

from .axis import YEARS, AGES

__all__ = ["sniff", "lines_of", "read_year_rows", "read_year_age_table",
           "read_waku_m", "read_waku_class", "read_block", "find_one"]


def sniff(path):
    """先頭行で文字コードを見分ける。原本の出力は UTF-8 か EUC-JP、基礎率ファイルの
    見出しは Shift_JIS（cp932）。どれでも読めなければ latin-1（数値だけ読む用）。"""
    head = open(path, "rb").readline()
    for enc in ("utf-8", "euc_jp", "cp932"):
        try:
            head.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def lines_of(path):
    return open(path, "rb").read().decode(sniff(path), "replace").splitlines()


def find_one(pattern, directory):
    hits = sorted(glob.glob(os.path.join(directory, pattern)))
    if not hits:
        raise FileNotFoundError("%s/%s" % (directory, pattern))
    return hits[0]


_NUM = re.compile(r"^\s*-?\d+\s*$")


def read_year_rows(path, year_base=0, skip_blank=True):
    """「年度ラベル, 値, 値, …」の行を {西暦: ndarray} に。

    ラベル列は整数。`year_base` を足して西暦にする（`KOKUKAITE` `kaitea`
    `cuta` は ラベル+2000、`waku-m` は西暦）。数値でない行（見出し・空行）は
    飛ばす。
    """
    out = {}
    for l in lines_of(path):
        f = [x.strip() for x in l.split(",")]
        if not f or not _NUM.match(f[0]):
            continue
        y = int(f[0]) + year_base
        vals = [x for x in f[1:] if x != ""]
        out[y] = np.array([float(x) for x in vals], dtype=np.float64)
    return out


def read_year_age_table(path, year_base=2000, first_age=0):
    """年度 × 年齢の表（`KOKUKAITE` `kaitea/b` `cuta`）を (YEARS.n, AGES.n) に置く。

    列は `first_age` 歳から連続とみなす。範囲外の年度・年齢は落とす
    （黙って巻き込まない）。表に無い年度は 0 のまま。
    """
    rows = read_year_rows(path, year_base)
    out = YEARS.zeros(AGES.n)
    for y, v in rows.items():
        if not YEARS.contains(y):
            continue
        last = first_age + len(v) - 1
        if last > AGES.last:
            raise ValueError("%s: 年齢 %d は軸の外" % (path, last))
        out[YEARS.i(y), AGES.s(first_age, last)] = v
    return out


def read_waku_m(path):
    """①の `waku-m.csv`（年度, 調整率）。西暦ラベル。"""
    rows = read_year_rows(path, 0)
    out = YEARS.zeros()
    for y, v in rows.items():
        if YEARS.contains(y):
            out[YEARS.i(y)] = v[0]
    return out


def read_waku_class(path):
    """①の `waku-NN.csv`（分類, 性, 年度, 計, 15歳, 16歳, …）。

    見出し行の年齢ラベルを読んで列を置く。戻り値は
    {(分類, 性): (YEARS.n, AGES.n) の配列} と 計の {(分類, 性): (YEARS.n,)}。
    """
    L = lines_of(path)
    hdr = None
    for i, l in enumerate(L):
        if l.startswith("分類,"):
            hdr = [x.strip() for x in l.split(",")]
            start = i + 1
            break
    if hdr is None:
        raise ValueError("%s: 見出し行（分類,性,年度,計,…）が無い" % path)
    ages = [int(x) for x in hdr[4:] if x != ""]
    tables, totals = {}, {}
    for l in L[start:]:
        f = [x.strip() for x in l.split(",")]
        if len(f) < 4 or not _NUM.match(f[0]) or not _NUM.match(f[2]):
            continue
        key = (int(f[0]), int(f[1]))
        y = int(f[2])
        if not YEARS.contains(y):
            continue
        if key not in tables:
            tables[key] = YEARS.zeros(AGES.n)
            totals[key] = YEARS.zeros()
        totals[key][YEARS.i(y)] = float(f[3])
        vals = [x for x in f[4:] if x != ""]
        for a, v in zip(ages, vals):
            tables[key][YEARS.i(y), AGES.i(a)] = float(v)
    return tables, totals


def read_block(path, title, header_offset, year_base, lines=None):
    """見出し行の直後に続く年度行を {西暦: {列名: 文字列}} に
    （`検証/オプション試算/compare_option.py:read_block` と同じ約束）。"""
    L = lines if lines is not None else lines_of(path)
    hits = [i for i, l in enumerate(L) if l.strip() == title]
    if not hits:
        hits = [i for i, l in enumerate(L) if l.startswith(title)]
    if not hits:
        raise ValueError("ブロック「%s」が無い: %s" % (title, path))
    start = hits[0]
    cols = [x.strip() for x in L[start + header_offset].split(",")]
    rows = {}
    for l in L[start + header_offset + 1:]:
        f = [x.strip() for x in l.split(",")]
        if not f or not _NUM.match(f[0]):
            if rows:
                break
            continue
        rows[int(f[0]) + year_base] = dict(zip(cols, f))
    if not rows:
        raise ValueError("ブロック「%s」に年度行が無い: %s" % (title, path))
    return rows
