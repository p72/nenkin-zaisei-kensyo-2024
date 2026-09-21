# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/flck.cpp の忠実移植（出力の先頭に来歴を書く）
==================================================================
`kiso.*` と `shus.*` の**先頭**に、読んだファイルの一覧と主な設定値を
書く。④基礎年金と⑤収支計算はこの部分を `read_headder` で読み飛ばし、
`#99-0000-0000` の行から本体を読み始める。

書く順番
--------
1. `readpath_map` の中身（キー名, 絶対パス）。`std::map` なので
   **キーの辞書順**（`econ`, `hk-1`, `hk-2`, …, `yuizor`）
2. `flck_param()` の19行（`KS, 20` から `flg_kozax, 0` まで）
3. `#99-0000-0000`

`kiso.*` と `shus.*` に**まったく同じ内容**を書く（19行の設定値も
一覧も同じ）。

原本の癖をそのまま残しているところ
----------------------------------
1. **`fprintf(fp, "#99-0000-0000\\n", "")` に余分な引数**
   （`flck.cpp:20,32`）。書式に変換指定が無いので `""` は捨てられる。
   ④の `printout.c:412` と同じ形。（`検証/原本の不具合.md`）

2. **`if(key == 11 || key == 12 || key == 13)` が2回続く。**
   `main.cpp` が `key` をこの3つに限っているので常に真。
   同じ `for` が2回丸ごと書かれている。

3. **`kzny` `daik14` `seidver` を出すが、`kzny` と `daik14` は
   どこからも代入されない**（0 のまま）。`seidver` は `main.cpp:36` が
   1 を入れる。

4. **`fp_map["kiso"]` を `operator[]` で引く。**キーが無ければ NULL を
   挿入して `fprintf(NULL, …)` で落ちるが、`fopn()` が
   `pseid == 0 || konen != 1` で必ず開くので届かない
   （`konen` が 1 になるのは `pseid == 0` のときだけ）。
"""
from glva import G
from setconst import KE, KIJUN, KS

__all__ = ["flck"]

# `flck_param()` が出す19項目（`flck.cpp:36-56`）。名前と値の取り方
_PARAM = (
    ("KS", lambda: KS),
    ("KE", lambda: KE),
    ("KIJUN", lambda: KIJUN),
    ("daik14", lambda: G.daik14),
    ("kzn", lambda: G.kzn),
    ("kzny", lambda: G.kzny),
    ("seidver", lambda: G.seidver),
    ("flg_kaisho", lambda: G.flg_kaisho),
    ("psly", lambda: G.psly),
    ("pslsi", lambda: G.pslsi),
    ("pslsi2", lambda: G.pslsi2),
    ("flg_hiho70", lambda: G.flg_hiho70),
    ("hiho70yr", lambda: G.hiho70yr),
    ("flg_part", lambda: G.flg_part),
    ("partyr1", lambda: G.partyr1),
    ("partyr2", lambda: G.partyr2),
    ("flg_hsr", lambda: G.flg_hsr),
    ("flg_sigo", lambda: G.flg_sigo),
    ("flg_kozax", lambda: G.flg_kozax),
)


def _flck_param(fp):
    """flck.cpp:36 の `flck_param`。"""
    for name, get in _PARAM:
        fp.write("%s, %d\n" % (name, get()))


def _write_head(fp):
    """読んだファイルの一覧＋設定値＋区切り行。"""
    # `std::map` はキーの辞書順
    for keystr, fullpath in sorted(G.readpath_map.items()):
        fp.write("%s, %s\n" % (keystr, fullpath))
    _flck_param(fp)
    fp.write("#99-0000-0000\n")      # 癖 1. 余分な引数は捨てられる


def flck():
    """flck.cpp:10 の忠実移植。癖 2. 同じ処理を2回書いている。"""
    if G.key == 11 or G.key == 12 or G.key == 13:
        _write_head(G.fp_map["kiso"])

    if G.key == 11 or G.key == 12 or G.key == 13:
        _write_head(G.fp_map["sh"])
