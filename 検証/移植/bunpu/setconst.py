# -*- coding: utf-8 -*-
"""
プログラム/分布推計/main.cpp の定数の忠実移植
=============================================
原本は `#define` を使わず main() の中に直接書いているので、名前を付けて
1箇所に集めた。値と並びは原本のまま。

原本の該当行
------------
    main.cpp:36  vector001  状態コードの一覧（20種）
    main.cpp:37  vector002  性別（1, 2）
    main.cpp:38  vector003  基準年齢（17, 27, 37, 47, 57, 62）
    main.cpp:39  main_var001 = 65   追う年数の上限
    main.cpp:48  vector012  4 × 105 × 2 × 55 の表（func10a が埋める）
    main.cpp:170 main_var006 = 1056000.0  賞与を含む上限の基準額
    main.cpp:112 vector025[i][0] = 996000.0 / … （i<275）
                                    924000.0 / … （それ以外）

`vector001` は `func09a`（prog09.cpp:5）が添字 0〜19 に写す集合と同じ。
`func09a` は**この20種以外を渡されると 99 を返す**ので、返り値を配列の
添字に使っている `func06a`/`func06b`（prog06.cpp）では範囲外になる。
実データでは起きないが、原本の作りとしては危うい
（`検証/原本の不具合.md` を参照）。
"""

# main.cpp:36 状態コード。func09a が 0〜19 に写す
STATE_CODES = [11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
               31, 32, 33, 34, 40, 50, 60, 70, 80, 99]

# main.cpp:37 性別
SEXES = [1, 2]

# main.cpp:38 基準年齢（コホート）
BASE_AGES = [17, 27, 37, 47, 57, 62]

# main.cpp:39 追う年数の上限。年次ループは
#   for (loop_var003 = loop_var002; loop_var003 < main_var001; ++loop_var003)
# なので、基準年齢 a のコホートは 65 - a 年ぶん回る
N_YEARS = 65

# main.cpp:48 vector012 の寸法
V012_SHAPE = (4, 105, 2, 55)

# main.cpp:170, 210, 212 賞与を含む上限の基準額
JOUGEN_BASE = 1056000.0

# main.cpp:110-114 総報酬の上限（i<275 と それ以外で切り替わる）
SOUHOUSHUU_HI = 996000.0
SOUHOUSHUU_LO = 924000.0
SOUHOUSHUU_SPLIT = 275

# prog05.cpp が読む初期母集団 CSV の列数
N_COLS_KISOSUU = 40

# prog06.cpp の func06a / func06b が var038 と比べる閾値
#   func06a: object01c==0 なら 414、そうでなければ基準年齢で 414〜474
#   func06b: 120 - (70 - 年度) * 12
FUNC06A_THRESHOLD_DEFAULT = 414
FUNC06A_THRESHOLD = {           # prog06.cpp:8-24（基準年齢 → 閾値）
    # arg06a8（基準年齢）が 51 以上なら 414
    49: 426, 50: 426,
    47: 438, 48: 438,
    45: 450, 46: 450,
    43: 462, 44: 462,
    # それ以外（42 以下）は 474
}
FUNC06A_THRESHOLD_LOW = 474

# prog09.cpp:65-83 func09c の支給開始年齢（基準年齢 → 年齢）
SHIKYUU_AGE_DEFAULT = 60
SHIKYUU_AGE = {                 # prog09.cpp:70-82
    49: 61, 50: 61,
    47: 62, 48: 62,
    45: 63, 46: 63,
    43: 64, 44: 64,
}
SHIKYUU_AGE_LOW = 65
