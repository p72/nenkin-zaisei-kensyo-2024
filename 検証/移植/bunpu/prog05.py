# -*- coding: utf-8 -*-
"""
プログラム/分布推計/prog05.cpp の忠実移植
=========================================
初期母集団の CSV（`kisosuu_set.csv`）を `class02` の並びに読み込む。

列と `varNNN` の対応（prog05.cpp:6-46 の順）

    列 0〜31   → var001〜var032    （int）
    列 32      → var035            （int）※ var033/var034 は読まない
    列 33      → var036            （int）
    （代入）    → var037 = 0
    列 34      → var038            （double）
    列 35      → var039            （double）
    列 36      → var040            （int）
    列 37      → var041            （double）
    列 38      → var042            （int）
    列 39      → var043            （double）

つまり CSV は **40列**で、`var033`/`var034`/`var044` は初期母集団から
読まない（`class02()` の初期値 0 のまま）。

`var033`/`var034` を読まないのは筋が通っている。この2つは「当年度の
厚年／基礎の月数」で、毎年 `func09c` が計算して入れるものだから、
初期値を持つ必要がない（`検証/原本の不具合.md` の B1 を参照）。

`std::stoi` と `std::stod` について
----------------------------------
- `std::stoi("12abc")` は 12 を返す（読める所まで読む）。読めなければ
  `std::invalid_argument` を**投げる**（`atoi` と違ってエラーになる）。
- `std::stod` も同じで、読めなければ投げる。
- 空文字列は投げる。

原本は例外を捕まえていないので、読めない値があればその場で
`terminate` する。移植でも同じ所で例外にする（`clib/cppnum.py`）。
"""
from cppnum import stod, stoi
from setconst import N_COLS_KISOSUU

__all__ = ["func05a"]


def func05a(arg05a1, arg05a2, arg05a3):
    """prog05.cpp:5 の忠実移植。

    `arg05a1` は人数、`arg05a2` は CSV（2次元の文字列）、
    `arg05a3` は `class02` のリスト（その場で埋める）。
    """
    for i in range(arg05a1):
        o = arg05a3[i]
        row = arg05a2[i]
        # 列 0〜31 → var001〜var032
        o.var001 = stoi(row[0])
        o.var002 = stoi(row[1])
        o.var003 = stoi(row[2])
        o.var004 = stoi(row[3])
        o.var005 = stoi(row[4])
        o.var006 = stoi(row[5])
        o.var007 = stoi(row[6])
        o.var008 = stoi(row[7])
        o.var009 = stoi(row[8])
        o.var010 = stoi(row[9])
        o.var011 = stoi(row[10])
        o.var012 = stoi(row[11])
        o.var013 = stoi(row[12])
        o.var014 = stoi(row[13])
        o.var015 = stoi(row[14])
        o.var016 = stoi(row[15])
        o.var017 = stoi(row[16])
        o.var018 = stoi(row[17])
        o.var019 = stoi(row[18])
        o.var020 = stoi(row[19])
        o.var021 = stoi(row[20])
        o.var022 = stoi(row[21])
        o.var023 = stoi(row[22])
        o.var024 = stoi(row[23])
        o.var025 = stoi(row[24])
        o.var026 = stoi(row[25])
        o.var027 = stoi(row[26])
        o.var028 = stoi(row[27])
        o.var029 = stoi(row[28])
        o.var030 = stoi(row[29])
        o.var031 = stoi(row[30])
        o.var032 = stoi(row[31])
        # var033 / var034 は読まない（毎年 func09c が入れる）
        o.var035 = stoi(row[32])
        o.var036 = stoi(row[33])
        o.var037 = 0
        o.var038 = stod(row[34])
        o.var039 = stod(row[35])
        o.var040 = stoi(row[36])
        o.var041 = stod(row[37])
        o.var042 = stoi(row[38])
        o.var043 = stod(row[39])
        # var044 も読まない


# 読む列数（番犬用）。上の対応表と食い違ったら気付けるように。
assert N_COLS_KISOSUU == 40
