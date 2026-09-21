# -*- coding: utf-8 -*-
"""
国民年金のグローバル変数（`m*.h` の `EXTERN`）の忠実移植
=========================================================
③はグローバルを**ヘッダの中で定義**する。`main.c` が

```c
#define MSEID_H_INCLUDED
…
#include "mseid.h"
```

と `*_H_INCLUDED` を先に立ててから `#include` するので、
`main.c` の翻訳単位では `EXTERN` が空（＝定義）になり、
ほかの .c では `extern`（＝宣言）になる。**C++ の古い流儀**で、
①④⑤の「`glva.c` に定義を並べる」のと同じことをしている。

置き場
------
| ヘッダ | 中身 |
|---|---|
| `mcntl.h` | 試算番号・経済前提・外枠の番号と旗（19行） |
| `mseid.h` | 制度の定数（加入可能年数・満額・単価） |
| `mecon.h` | 経済前提を当てはめたあとの年金額 |
| `mkisoritu.h` | 基礎率（脱退力・失権率・発生割合・給付率） |
| `mkisosu.h` | 基礎数（外枠・被保険者・受給者）と **8つの `struct`** |
| `mfile_open.h` | ファイルの名前とハンドル（入力86・出力11） |
| `option.h` | 45年化などのオプションと従来の外枠 |

年度と年齢の添字
----------------
③は**西暦をそのまま添字にしない**。`nendo - SHONENDO`（SHONENDO =
2020）、`nenrei - MIN_HIHO_NENREI`（= 20）のように引いて使う。
②（`k` = 西暦 − 2000 で負にもなる）とは別の流儀。

配列の寸法は**ヘッダに書いてある式のまま**にしてある
（`SAISHUNENDO - SHONENDO + 1` など）。定数を差し替えれば
寸法も付いてくる。

8つの `struct` は NumPy の構造化 dtype にする
---------------------------------------------
```c
struct hihokensha {
  double ninzu;
  double kikan;
  double noufu;
  double menjo[MENJO_DANKAI][KOKKO_HIKIAGE];
  double gakusei;
  double wakamono;
  double fuka;
};
```

を

```python
HIHOKENSHA = np.dtype([
    ("ninzu", "f8"), ("kikan", "f8"), ("noufu", "f8"),
    ("menjo", "f8", (MENJO_DANKAI, KOKKO_HIKIAGE)),
    ("gakusei", "f8"), ("wakamono", "f8"), ("fuka", "f8")])
```

と写す。**欄の並びも C と同じ**にしてあるので、`.tobytes()` の
並びが C の構造体の並びと一致する（`double` だけなので詰め物も
入らない）。ハーネスと CRC32 で突き合わせられる。

`struct` の演算（`scalar` `add` `multiply` `nendokan` …）は
`str_op.py` に写す。

`*_Zero` は「全部 0 の1個」
--------------------------
`Hihokensha_Zero` `Rorei_Zero` などは**代入で 0 に戻すための見本**で、
`zero()` で使う。原本は 0 初期化のグローバルなのでそのまま 0。
移植版も長さ0次元の構造化配列にする。

大きさ
------
全部で **1,180MB**。いちばん大きいのは

    Hihokensha / Hihokensha2 / Taikisha  各 (106, 51, 51) × 21 欄 = 46MB
    Rorei / Rorei_Kyu / Turo_Kyu         各 (10, 106, 54, 12) × 欄
    Noufuritu                            (7, 106, 51, 11) = 33MB

②の 2,566MB より小さい。
"""
import numpy as np

from setconst import (ECON_SHONENDO, I_KEINEN_SHONENDO, INFILE_NUM,
                      KOKKO_HIKIAGE, KURI_AGE_SAGE_SHIKYU_KUBUN,
                      MAX_HIHO_KIKAN, MAX_HIHO_NENREI, MAX_IZOKU_KO_JUKYU,
                      MAX_IZOKU_OTTO_JUKYU, MAX_IZOKU_TUMA_JUKYU,
                      MAX_KAFU_JUKYU, MAX_ROREI_JUKYU, MAX_SHOGAI_JUKYU,
                      MAX_SHUBETU, MAX_WAKU_NENREI, MENJO_DANKAI,
                      MENJO_JOKYO, MIN_HIHO_NENREI, MIN_IZOKU_KO_JUKYU,
                      MIN_IZOKU_OTTO_JUKYU, MIN_IZOKU_TUMA_JUKYU,
                      MIN_KAFU_JUKYU, MIN_ROREI_JUKYU, MIN_SHOGAI_JUKYU,
                      MIN_WAKU_NENREI, NENREI_SUM, N_O_NENDO, OUTFILE_NUM,
                      SAISHUNENDO, SEIBETU, SHIBOU_KUBUN, SHIKKENRITU_MAX,
                      SHIKKENRITU_MIN, SHOGAI_TOKYU, SHONENDO,
                      SOTOWAKU_SHONENDO, SUIKEISHONENDO)

__all__ = ["G", "HIHOKENSHA", "ROREI", "ROREI_KYU", "GONEN", "SHOGAI",
           "IZOKU", "KAFU", "ICHIJIKIN", "zero_init", "STRUCT_DTYPES"]

# ---- 8つの struct（欄の並びは C と同じ）----------------------------
HIHOKENSHA = np.dtype([
    ("ninzu", "f8"),
    ("kikan", "f8"),
    ("noufu", "f8"),
    ("menjo", "f8", (MENJO_DANKAI, KOKKO_HIKIAGE)),
    ("gakusei", "f8"),
    ("wakamono", "f8"),
    ("fuka", "f8"),
])

ROREI = np.dtype([
    ("ninzu", "f8"),
    ("noufu", "f8"),
    ("menjo", "f8", (MENJO_DANKAI, KOKKO_HIKIAGE)),
    ("rofuku_shitasasae", "f8"),
    ("fuka", "f8"),
])

ROREI_KYU = np.dtype([
    ("ninzu", "f8"),
    ("noufu", "f8"),
    ("menjo", "f8"),
    ("kasa_noufu", "f8"),
    ("kasa_menjo", "f8"),
    ("rofuku_shitasasae", "f8"),
    ("fuka", "f8"),
])

GONEN = np.dtype([
    ("ninzu", "f8"),
    ("noufu", "f8"),
])

SHOGAI = np.dtype([
    ("ninzu", "f8"),
    ("kihon", "f8"),
    ("kakyu", "f8"),
    ("menjo_kihon", "f8"),
    ("menjo_kakyu", "f8"),
])

IZOKU = np.dtype([
    ("ninzu", "f8"),
    ("kihon", "f8"),
    ("kakyu", "f8"),
])

KAFU = np.dtype([
    ("ninzu", "f8"),
    ("noufu", "f8"),
    ("menjo", "f8", (MENJO_DANKAI, KOKKO_HIKIAGE)),
])

ICHIJIKIN = np.dtype([
    ("ninzu", "f8"),
    ("kyufu", "f8"),
    ("kyufu_fuka", "f8"),
])

STRUCT_DTYPES = {
    "hihokensha": HIHOKENSHA, "rorei": ROREI, "rorei_kyu": ROREI_KYU,
    "gonen": GONEN, "shogai": SHOGAI, "izoku": IZOKU, "kafu": KAFU,
    "ichijikin": ICHIJIKIN,
}

# 使い回す寸法（ヘッダに書いてある式そのまま）
_NENDO = SAISHUNENDO - SHONENDO + 1                       # 106
_SOTOWAKU_NENDO = SAISHUNENDO - SOTOWAKU_SHONENDO + 1     # 105
_WAKU_NENREI = MAX_WAKU_NENREI - MIN_WAKU_NENREI + 1      # 86
_HIHO_N1 = MAX_HIHO_NENREI - MIN_HIHO_NENREI + 1          # 51
_HIHO_N2 = MAX_HIHO_NENREI - MIN_HIHO_NENREI + 2          # 52（計の欄つき）
_KIKAN = MAX_HIHO_KIKAN + 1                               # 51
_ROREI_N = MAX_ROREI_JUKYU - MIN_ROREI_JUKYU + 1          # 56
_ROREI_SUM = MAX_ROREI_JUKYU - NENREI_SUM + 1             # 54
_KAS = KURI_AGE_SAGE_SHIKYU_KUBUN                         # 11
_SHUB3 = MAX_SHUBETU + 3                                  # 10
_SHOGAI_N = MAX_SHOGAI_JUKYU - MIN_SHOGAI_JUKYU + 1       # 96
_SHOGAI_SUM = MAX_SHOGAI_JUKYU - NENREI_SUM + 1           # 54
_TUMA_N = MAX_IZOKU_TUMA_JUKYU - MIN_IZOKU_TUMA_JUKYU + 1  # 100
_TUMA_SUM = MAX_IZOKU_TUMA_JUKYU - NENREI_SUM + 1          # 54
_OTTO_N = MAX_IZOKU_OTTO_JUKYU - MIN_IZOKU_OTTO_JUKYU + 1  # 98
_OTTO_SUM = MAX_IZOKU_OTTO_JUKYU - NENREI_SUM + 1          # 54
_KO_N = MAX_IZOKU_KO_JUKYU - MIN_IZOKU_KO_JUKYU + 1        # 20
_KAFU_N = MAX_KAFU_JUKYU - MIN_KAFU_JUKYU + 1              # 39
_ICHIJI_SUM = MAX_HIHO_NENREI - NENREI_SUM + 1             # 9

# ---- mkisosu.h（基礎数）-------------------------------------------
_KISOSU = [
    ("Sotowaku", (MAX_SHUBETU, _SOTOWAKU_NENDO, _WAKU_NENREI)),
    ("Sotowaku_2gou", (SEIBETU, _SOTOWAKU_NENDO, _WAKU_NENREI)),
    ("Hiho_Kei", (MAX_SHUBETU, _NENDO, _HIHO_N2)),
    ("Hiho_Noufu", (MAX_SHUBETU, _NENDO, _HIHO_N2)),
    ("Hiho_Menjo", (MAX_SHUBETU, _NENDO, _HIHO_N2, MENJO_JOKYO)),
    ("Fuka_Hiho", (MAX_SHUBETU, _NENDO, _HIHO_N2)),
    ("Hiho_Kei_P", (MAX_SHUBETU, _NENDO, _HIHO_N2)),
    ("Hiho_Noufu_P", (MAX_SHUBETU, _NENDO, _HIHO_N2)),
    ("Hiho_Menjo_P", (MAX_SHUBETU, _NENDO, _HIHO_N2, MENJO_JOKYO)),
    ("Fuka_Hiho_P", (MAX_SHUBETU, _NENDO, _HIHO_N2)),
    ("Hiho_Kei_Nendokan", (MAX_SHUBETU, _NENDO, _HIHO_N2)),
    ("Hiho_Noufu_Nendokan", (MAX_SHUBETU, _NENDO, _HIHO_N2)),
    ("Hiho_Menjo_Nendokan", (MAX_SHUBETU, _NENDO, _HIHO_N2, MENJO_JOKYO)),
    ("Fuka_Hiho_Nendokan", (MAX_SHUBETU, _NENDO, _HIHO_N2)),
    ("Hiho_Sankyu", (_NENDO, _HIHO_N1)),
    ("Hiho_Sankyu_Sum", (_NENDO,)),
    ("Hiho_Ikukyu", (_HIHO_N1,)),
    ("Hiho_Ikukyu_Sum", (_NENDO,)),
]

# ---- mkisoritu.h（基礎率）-----------------------------------------
_KISORITU = [
    ("Dattairyoku_Gokei", (_NENDO, _HIHO_N1)),
    ("Dattairyoku_Shibou", (_NENDO, _HIHO_N1)),
    ("Saikanyuritu", (_NENDO, _HIHO_N1)),
    ("q", (SHIKKENRITU_MAX - SHIKKENRITU_MIN + 1,
           MAX_ROREI_JUKYU - 1 - 0 + 1, 2)),
    ("Noufuritu", (MAX_SHUBETU, _NENDO, _HIHO_N1, MENJO_JOKYO)),
    ("Noufuritu_Fuka", (MAX_SHUBETU, _NENDO, _HIHO_N1)),
    ("Hassei_Wariai_Rorei", (_NENDO, _KAS)),
    ("Shikkenritu_Rorei", (_NENDO, MAX_ROREI_JUKYU - MIN_HIHO_NENREI + 1)),
    ("Waribikiritu", (2, 2, 70 - 66 + 1,
                      SUIKEISHONENDO + 10 - SUIKEISHONENDO + 1 + 1)),
    ("Kyufu_ritu", (_KAS, (SAISHUNENDO - MIN_ROREI_JUKYU)
                    - (SHONENDO - 70) + 1, 2)),
    ("Kyufu_ritu1", (_KAS, (SAISHUNENDO - MIN_ROREI_JUKYU)
                     - (SHONENDO - 70) + 1, 2)),
    ("Kyufu_ritu2", (_KAS, (SAISHUNENDO - MIN_ROREI_JUKYU)
                     - (SHONENDO - 70) + 1, 2)),
    ("Hasseiryoku_Shogai", (_NENDO, _HIHO_N1)),
    ("Hassei_Wariai_20mae", (_NENDO, _HIHO_N1)),
    ("Shikkenritu_Ippan", (_NENDO, _SHOGAI_N)),
    ("Shikkenritu_20mae", (_NENDO, _SHOGAI_N)),
    ("Tokyu_Wariai_20mae", (_NENDO, SHOGAI_TOKYU)),
    ("Tokyu_Wariai_Ippan", (_NENDO, SHOGAI_TOKYU)),
    ("Kakyu_Wariai_Ippan_12shi", (_NENDO, _SHOGAI_N)),
    ("Kakyu_Wariai_Ippan_3shiiko", (_NENDO, _SHOGAI_N)),
    ("Kakyu_Wariai_20mae_12shi", (_NENDO, _SHOGAI_N)),
    ("Kakyu_Wariai_20mae_3shiiko", (_NENDO, _SHOGAI_N)),
    ("Hassei_Wariai_Tuma", (_NENDO, _HIHO_N1)),
    ("Hassei_Wariai_Otto", (_NENDO, _HIHO_N1)),
    ("Hassei_Wariai_Ko", (_NENDO, _HIHO_N1)),
    ("Hassei_Wariai_Kafu", (_NENDO, _HIHO_N1)),
    ("Hassei_Wariai_Shibou", (_NENDO, _HIHO_N1)),
    ("Shikkenritu_Tuma", (_NENDO, _TUMA_N)),
    ("Shikkenritu_Otto", (_NENDO, _OTTO_N)),
    ("Shikkenritu_Ko", (_NENDO, _KO_N)),
    ("Shikkenritu_Kafu", (_NENDO, _KAFU_N)),
    ("Sokan_Tuma", (_NENDO, _HIHO_N1)),
    ("Sokan_Otto", (_NENDO, _HIHO_N1)),
    ("Sokan_Ko", (_NENDO, _HIHO_N1)),
    ("Sokan_Kafu", (_NENDO, _HIHO_N1)),
    ("Kakyu_Wariai_Tuma_12shi", (_NENDO, _TUMA_N)),
    ("Kakyu_Wariai_Tuma_3shiiko", (_NENDO, _TUMA_N)),
    ("Kakyu_Wariai_Otto_12shi", (_NENDO, _OTTO_N)),
    ("Kakyu_Wariai_Otto_3shiiko", (_NENDO, _OTTO_N)),
    ("Kakyu_Wariai_Ko_12shi", (_NENDO, _KO_N)),
    ("Kakyu_Wariai_Ko_3shiiko", (_NENDO, _KO_N)),
    ("Shikyuritu_Gonen", (_NENDO, _ROREI_N)),
    ("Shikyuritu_Shogai_Ippan", (_NENDO, _SHOGAI_N, SHOGAI_TOKYU)),
    ("Shikyuritu_Shogai_Ippan_keinen", (_NENDO, _SHOGAI_N, SHOGAI_TOKYU)),
    ("Shikyuritu_Shogai_20mae", (_NENDO, _SHOGAI_N, SHOGAI_TOKYU)),
    ("Shikyuritu_Shogai_20mae_keinen", (_NENDO, _SHOGAI_N, SHOGAI_TOKYU)),
    ("Shikyuritu_Shogai_Kyu", (_NENDO, _SHOGAI_N, SHOGAI_TOKYU)),
    ("Shikyuritu_Shogai_Kyu_keinen", (_NENDO, _SHOGAI_N, SHOGAI_TOKYU)),
    ("Shikyuritu_Tuma", (_NENDO,)),
    ("Shikyuritu_Otto", (_NENDO,)),
    ("Shikyuritu_Ko", (_NENDO,)),
    ("Shikyuritu_Kafu", (_NENDO, MAX_KAFU_JUKYU - 60 + 1)),
    ("Izoku_Keinen", (SAISHUNENDO - I_KEINEN_SHONENDO + 1, _HIHO_N1, 2)),
]

# ---- mseid.h（制度の定数）-----------------------------------------
_SEID = [
    ("Kanou_Nensu", (_NENDO, SAISHUNENDO - N_O_NENDO + 1)),
    ("Full_Pension_Shonendo", (_NENDO, SAISHUNENDO - N_O_NENDO + 1)),
    ("Tanka_Shibou_Shonendo", (SHIBOU_KUBUN,)),
    ("Hokenryou_Wariai", (MENJO_DANKAI,)),
    ("Shogai_Bairitu", (SHOGAI_TOKYU,)),
    ("Kokko_Wariai", (KOKKO_HIKIAGE,)),
]

# ---- mecon.h（経済前提を当てはめたあと）---------------------------
_ECON = [
    ("Full_Pension", (_NENDO, MAX_ROREI_JUKYU + 1)),
    ("Kakyu_Tanka_12shi", (_NENDO, MAX_ROREI_JUKYU + 1)),
    ("Kakyu_Tanka_3shiiko", (_NENDO, MAX_ROREI_JUKYU + 1)),
    ("Tanka_Shibou", (_NENDO, SHIBOU_KUBUN)),
    ("kaiteiritu_tannen", (SAISHUNENDO - ECON_SHONENDO + 1,
                           MAX_ROREI_JUKYU + 1)),
]

# ---- option.h ------------------------------------------------------
_OPTION = [
    ("Sotowaku_Jurai", (MAX_SHUBETU, _SOTOWAKU_NENDO, _WAKU_NENREI)),
]

# 素の double 配列（ぜんぶ）
_DOUBLE_ARRAYS = _KISOSU + _KISORITU + _SEID + _ECON + _OPTION

# ---- struct の配列 -------------------------------------------------
_STRUCT_ARRAYS = [
    # mkisosu.h:40-45
    ("Hihokensha", HIHOKENSHA, (_NENDO, _HIHO_N1, _KIKAN)),
    ("Taikisha", HIHOKENSHA, (_NENDO, _HIHO_N1, _KIKAN)),
    ("Hihokensha_Zero", HIHOKENSHA, ()),
    ("Taikisha_Zero", HIHOKENSHA, ()),
    ("Hihokensha2", HIHOKENSHA, (_NENDO, _HIHO_N1, _KIKAN)),
    ("Hihokensha_Shibou2", HIHOKENSHA, (_HIHO_N1, _KIKAN)),
    # mkisosu.h:55-61
    ("Rorei_Nendomatu", ROREI, (_NENDO, _ROREI_N, _KAS)),
    ("Rorei_Ichibu_Nendomatu", ROREI, (_NENDO, _ROREI_N, _KAS)),
    ("Rorei", ROREI, (_SHUB3, _NENDO, _ROREI_SUM, _KAS + 1)),
    ("Shikyuritu_Rorei", ROREI, (_NENDO, _ROREI_N)),
    ("Kakudai_Ichibu", ROREI,
     (SAISHUNENDO - MIN_ROREI_JUKYU - (SHONENDO - MAX_ROREI_JUKYU) + 1,
      _KAS)),
    ("Rorei_Zero", ROREI, ()),
    ("Rorei_Shinki2", ROREI, (_KAS,)),
    # mkisosu.h:73-79
    ("Rorei_Kyu_Nendomatu", ROREI_KYU, (_NENDO, _ROREI_N, _KAS)),
    ("Rorei_Kyu", ROREI_KYU, (_SHUB3, _NENDO, _ROREI_SUM, _KAS + 1)),
    ("Shikyuritu_Rorei_Kyu", ROREI_KYU, (_NENDO, _ROREI_N)),
    ("Turo_Kyu_Nendomatu", ROREI_KYU, (_NENDO, _ROREI_N, _KAS)),
    ("Turo_Kyu", ROREI_KYU, (_SHUB3, _NENDO, _ROREI_SUM, _KAS + 1)),
    ("Shikyuritu_Turo_Kyu", ROREI_KYU, (_NENDO, _ROREI_N)),
    ("Rorei_Kyu_Zero", ROREI_KYU, ()),
    # mkisosu.h:86-88
    ("Gonen_Nendomatu", GONEN, (_NENDO, _ROREI_N, _KAS)),
    ("Gonen", GONEN, (_SHUB3, _NENDO, _ROREI_SUM, _KAS + 1)),
    ("Gonen_Zero", GONEN, ()),
    # mkisosu.h:98-104
    ("Shogai_Ippan_Nendomatu", SHOGAI, (_NENDO, _SHOGAI_N, SHOGAI_TOKYU)),
    ("Shogai_Ippan", SHOGAI, (_SHUB3, _NENDO, _SHOGAI_SUM)),
    ("Shogai_20mae_Nendomatu", SHOGAI, (_NENDO, _SHOGAI_N, SHOGAI_TOKYU)),
    ("Shogai_20mae", SHOGAI, (_SHUB3, _NENDO, _SHOGAI_SUM)),
    ("Shogai_Kyu_Nendomatu", SHOGAI, (_NENDO, _SHOGAI_N, SHOGAI_TOKYU)),
    ("Shogai_Kyu", SHOGAI, (_SHUB3, _NENDO, _SHOGAI_SUM)),
    ("Shogai_Zero", SHOGAI, ()),
    # mkisosu.h:112-118
    ("Izoku_Tuma_Nendomatu", IZOKU, (_NENDO, _TUMA_N)),
    ("Izoku_Tuma", IZOKU, (_SHUB3, _NENDO, _TUMA_SUM)),
    ("Izoku_Otto_Nendomatu", IZOKU, (_NENDO, _OTTO_N)),
    ("Izoku_Otto", IZOKU, (_SHUB3, _NENDO, _OTTO_SUM)),
    ("Izoku_Ko_Nendomatu", IZOKU, (_NENDO, _KO_N)),
    ("Izoku_Ko", IZOKU, (_SHUB3, _NENDO)),
    ("Izoku_Zero", IZOKU, ()),
    # mkisosu.h:126-130
    ("Kafu_Nendomatu", KAFU, (_NENDO, _KAFU_N)),
    ("Kafu", KAFU, (_SHUB3, _NENDO)),
    ("Kafu_Kyu_Nendomatu", KAFU, (_NENDO, _KAFU_N)),
    ("Kafu_Kyu", KAFU, (_SHUB3, _NENDO)),
    ("Kafu_Zero", KAFU, ()),
    # mkisosu.h:138-140
    ("Ichijikin_Nendomatu", ICHIJIKIN, (_NENDO, _HIHO_N1)),
    ("Ichijikin", ICHIJIKIN, (_SHUB3, _NENDO, _ICHIJI_SUM)),
    ("Ichijikin_Zero", ICHIJIKIN, ()),
]

# ---- スカラー（`mcntl.h` `mseid.h` `option.h`）---------------------
_INT_SCALARS = (
    # mcntl.h
    "Kako_Saimu", "TINSURA", "Kugiri_Nendo", "Jyukyusha_Nomi",
    # option.h
    "Part", "Part_Year", "Option", "OPTION_START", "OP_HIKIAGE_KANKAKU",
)
_DBL_SCALARS = (
    # mcntl.h
    "Kisai_Shitasasae",
    # mseid.h
    "Full_Pension_Fuka", "Kakyu_Tanka_12shi_Shonendo",
    "Kakyu_Tanka_3shiiko_Shonendo", "Tanka_Shibou_Fuka",
)
_STR_SCALARS = (
    # mcntl.h（`char KOKUNEN[7]` など。長さの上限は原本のまま）
    ("KOKUNEN", 7), ("ECON", 5), ("SOTOWAKU", 5), ("SOTOWAKU_JURAI", 5),
    ("Version", 20), ("BIRTHFILE", 2), ("DEATH", 2),
)


class _Globals(object):
    """③のグローバル変数を1つにまとめた入れ物。

    原本はヘッダの中のファイルスコープなので、モジュールを跨いで
    同じ実体を見る。移植版も1つの実体（`G`）を共有する。

    宣言に無い名前を触ったら **`AttributeError` にする**（打ち間違いを
    そのまま新しい変数にしてしまわないように）。
    """

    __slots__ = (tuple(n for n, _s in _DOUBLE_ARRAYS)
                 + tuple(n for n, _d, _s in _STRUCT_ARRAYS)
                 + _INT_SCALARS + _DBL_SCALARS
                 + tuple(n for n, _w in _STR_SCALARS)
                 + ("fp_in", "fp_out", "infile_name", "outfile_name")
                 # `siml.c` の `static` な局所配列（呼び出しをまたいで
                 # 残る）。`siml.py` が最初の呼び出しで作る
                 + ("_siml_static",))

    def __init__(self):
        zero_init(self)

    # ---- 確かめ用 ----
    def allocated(self):
        """確保した double の数（`struct` の欄も数える）。"""
        n = 0
        for name, _s in _DOUBLE_ARRAYS:
            n += getattr(self, name).size
        for name, dt, _s in _STRUCT_ARRAYS:
            a = getattr(self, name)
            n += a.size * (dt.itemsize // 8)
        return n

    def allocated_mb(self):
        return self.allocated() * 8 / 1024.0 / 1024.0


def zero_init(g=None):
    """`main.c` に入った時点のグローバルの姿（C の 0 初期化）。

    ③には `zero()` の宣言（`snaps.h:139`）はあるが**定義が無い**
    （`検証/原本の不具合.md` F を参照）。C のグローバルは 0 で
    始まるので、その姿をここで作る。
    """
    if g is None:
        g = G
    for name, shape in _DOUBLE_ARRAYS:
        setattr(g, name, np.zeros(shape, dtype=np.float64))
    for name, dt, shape in _STRUCT_ARRAYS:
        setattr(g, name, np.zeros(shape, dtype=dt))
    for name in _INT_SCALARS:
        setattr(g, name, 0)
    for name in _DBL_SCALARS:
        setattr(g, name, 0.0)
    for name, _w in _STR_SCALARS:
        setattr(g, name, "")
    # `mfile_open.h` のファイルハンドルと名前
    g.fp_in = [None] * INFILE_NUM
    g.fp_out = [None] * OUTFILE_NUM
    g.infile_name = [""] * INFILE_NUM
    g.outfile_name = [""] * OUTFILE_NUM
    return g


G = _Globals()
