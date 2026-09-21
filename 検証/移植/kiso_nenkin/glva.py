# -*- coding: utf-8 -*-
"""
基礎年金の mcntl.h / mecon.h / mkisosu.h / mkiso.h / option.h / mfile_open.h
==============================================================================
原本はグローバル変数の塊。⑤⑥①と同じで、`m` 付きのヘッダが定義、
`m` なしが `extern` 宣言……のはずだが**④には `m` なしのヘッダが無い**。
代わりに `main.c` が

```c
#define MCNTL_H_INCLUDED
...
#include "mcntl.h"
```

と全部のガードを**先に立ててから** include する。ヘッダ側は

```c
#ifdef MCNTL_H_INCLUDED
    #define EXTERN          /* ← 中身が空。つまり定義になる */
#else
    #define EXTERN extern
#endif
```

なので、`main.c` の翻訳単位だけが実体を持ち、他の `.c` は `extern`
宣言になる。`#ifdef` と `#define` が逆（ガードを立てた方が定義側）で、
インクルードガードとしては働いていない。

移植では1個の `G` オブジェクトに全部ぶら下げる。名前は原本と1文字も
変えていない。配列は NumPy の `float64`（C の double 配列と同じメモリ
配置）で、初回アクセス時に確保する。

いちばん大きい6つ
-----------------
    Kyufu / Kyufu_Nendomatu / Kyufu_Nendomatu_P         各 29.7MB
    Kasanmae_Kyufu / _Nendomatu / _Nendomatu_P          各 29.7MB

寸法は `[6][106][54][3][4][3][3]` = 3,709,152 要素。この6本で 178MB、
全部で約 260MB。原本は静的領域に置いている。

添字の意味
----------
    seido  0 制度計 / 1 国年 / 2 厚年 / 3 国共 / 4 地共 / 5 私学
           （`Tumatumi` だけ 6 = 分配前の妻積を足した7要素）
    年度   人数・給付費は `nendo - SHONENDO`（0〜105）
           経済前提は `nendo - ECON_SHONENDO`（0〜124）
           `Tumatumi` は `nendo - TUMATUMI_NENDO`（0〜110）
    年齢   給付費は `nenrei - NENREI_SUM`（0 が年齢計、1〜53 が 63〜115）
           改定率は `nenrei - UNDER_67`（0〜48 が 67〜115）
           `Cut_ritu` は `nenrei - UNDER_63`（0〜52 が 63〜115）
    shinkyu   0 計 / 1 新法 / 2 旧法
    kubun     0 計 / 1 老齢 / 2 障害 / 3 遺族
    taishou   0 計 / 1 拠出 / 2 特別
    keitai    0 計 / 1 基本 / 2 加給

原本の癖をそのまま残しているところ
----------------------------------
1. **`Fuka`（配列）と `FUKA`（定数 2）が大文字小文字だけ違う。**
   `mkiso.h` の `double Fuka[...]` と `snaps.h` の `#define FUKA 2`。
   移植版では `G.Fuka` と `setconst.FUKA` に分かれる。

2. **`cut_ruiseki` が `[125][125][54]` で 6.75MB。**うち実際に使うのは
   `c_nendo >= 2005`、`nendo >= 2023` の範囲だけ。`dtst()` が全体を
   1.0 で埋める（106 万要素の三重ループ）。

3. **`Kasan_Sum` はどこからも読まれない。**`option.h` で
   `[6][106][54][3]` を宣言しているが、代入も参照も1か所も無い。
   移植版では確保するだけにしてある（`__getattr__` があるので
   触らなければメモリも取らない）。
"""
import numpy as np

from setconst import (
    NC, NE, NJ, NY, SAISHUNENDO, SEIDO_KUBUN, SEIBETU, SHIKYU_KEITAI,
    SHINKYU, KYUFU_HOUHOU, KYUFU_KUBUN, KYUFU_TAISHOU, NOUFU_JOTAI_KYU,
    NOUFU_JOTAI_SHIN, TOKUBETU_SHURUI, TUMATUMI_NENDO, SHONENDO,
    MAX_JUKYU, UNDER_63, INFILE_NUM, OUTFILE_NUM,
)

__all__ = ["Glva", "G"]

# ---------------------------------------------------------------------------
# **0 で割っても落ちないようにする。**①⑥と同じ理由。
#
# ④には分母のゼロを確かめていない割り算がある。`SanteiTaishou` は
# `SHONENDO`（2020）年度が 0 なので、`tumatumi_cal_jisseki` や
# `Atamawari_cut` の頭割りで 0/0 が起きる。C は IEEE 754 どおり nan を
# 返して進むので、移植版も同じでなければならない。
#
# そこで**配列の値は `np.float64` のまま扱う**（`float()` に落とさない）。
# `np.float64` の四則演算は IEEE 754 倍精度そのもので Python の float と
# 同じ結果になるが、0 除算だけは C と同じく nan / ±inf を返す。
# ---------------------------------------------------------------------------
np.seterr(divide="ignore", invalid="ignore", over="ignore", under="ignore")

# --------------------------------------------------------------------------
# 配列の寸法表。原本のヘッダの宣言をそのまま並べたもの。
# --------------------------------------------------------------------------
_ARRAYS = {
    # ---- mcntl.h ----
    # double hosei_shin[KYUFU_KUBUN][SAISHUNENDO - SHONENDO + 1];
    "hosei_shin": (KYUFU_KUBUN, NY),
    # double hosei_kyu[6][SAISHUNENDO - SHONENDO + 1];
    "hosei_kyu": (6, NY),

    # ---- mecon.h ----
    "cpi_up": (NE,),
    "base_up": (NE,),
    "base_up_k": (NE,),
    "interest_rate": (NE,),
    "kakaku": (NE,),
    # double pre_cut[125][MAX_JUKYU - UNDER_67 + 1];
    "pre_cut": (NE, NC),
    "T": (NE, NC),
    # double cut_ruiseki[125][125][MAX_JUKYU - NENREI_SUM + 1];   6.75MB
    "cut_ruiseki": (NE, NE, NJ),
    "ruiseki_interest_rate": (NE,),
    "g_ruiseki_interest_rate": (NE,),
    "kaiteiritu": (NE, NC),
    "kaiteiritu_cut": (NE, NC),

    # ---- mkisosu.h ----
    "Rorei_New": (SEIDO_KUBUN, NY, NJ, SEIBETU, NOUFU_JOTAI_SHIN),
    "Shogai_New": (SEIDO_KUBUN, NY, NJ, SEIBETU, KYUFU_HOUHOU,
                   SHIKYU_KEITAI),
    "Izoku_New": (SEIDO_KUBUN, NY, NJ, SEIBETU, SHIKYU_KEITAI),
    "Rorei_Old": (SEIDO_KUBUN, NY, NJ, SEIBETU, NOUFU_JOTAI_KYU),
    "Shogai_Old": (SEIDO_KUBUN, NY, NJ, SEIBETU, SHIKYU_KEITAI,
                   NOUFU_JOTAI_KYU - 6),
    "Izoku_Old": (SEIDO_KUBUN, NY, NJ, SEIBETU, SHIKYU_KEITAI,
                  NOUFU_JOTAI_KYU - 6),
    "FurikaeKasan": (SEIDO_KUBUN, NY, NJ, SEIBETU, KYUFU_KUBUN - 1),
    # 29.7MB × 3
    "Kyufu": (SEIDO_KUBUN, NY, NJ, SHINKYU, KYUFU_KUBUN, KYUFU_TAISHOU,
              SHIKYU_KEITAI),
    "Kyufu_Nendomatu": (SEIDO_KUBUN, NY, NJ, SHINKYU, KYUFU_KUBUN,
                        KYUFU_TAISHOU, SHIKYU_KEITAI),
    "Kyufu_Nendomatu_P": (SEIDO_KUBUN, NY, NJ, SHINKYU, KYUFU_KUBUN,
                          KYUFU_TAISHOU, SHIKYU_KEITAI),
    "Kokko": (SEIDO_KUBUN, NY, NJ, SHINKYU, KYUFU_KUBUN, SHIKYU_KEITAI),
    "Kokko_Nendomatu": (SEIDO_KUBUN, NY, NJ, SHINKYU, KYUFU_KUBUN,
                        SHIKYU_KEITAI),
    "Kokko_Nendomatu_P": (SEIDO_KUBUN, NY, NJ, SHINKYU, KYUFU_KUBUN,
                          SHIKYU_KEITAI),
    "Kyoshutukin": (SEIDO_KUBUN, NY, NJ, SHIKYU_KEITAI),
    "Kyoshutukin_Nendomatu": (SEIDO_KUBUN, NY, NJ, SHIKYU_KEITAI),
    "Kyoshutukin_Nendomatu_P": (SEIDO_KUBUN, NY, NJ, SHIKYU_KEITAI),
    "Kyoshutukin_Kokko": (SEIDO_KUBUN, NY, NJ, SHIKYU_KEITAI),
    "Kyoshutukin_Kokko_Nendomatu": (SEIDO_KUBUN, NY, NJ, SHIKYU_KEITAI),
    "Kyoshutukin_Kokko_Nendomatu_P": (SEIDO_KUBUN, NY, NJ, SHIKYU_KEITAI),
    "Tanka": (NY, NJ, SHIKYU_KEITAI),
    "Tanka_Nendomatu": (NY, NJ, SHIKYU_KEITAI),
    "Tanka_Nendomatu_P": (NY, NJ, SHIKYU_KEITAI),
    "Tanka_Kokko": (NY, NJ, SHIKYU_KEITAI),
    "Tanka_Kokko_Nendomatu": (NY, NJ, SHIKYU_KEITAI),
    "Tanka_Kokko_Nendomatu_P": (NY, NJ, SHIKYU_KEITAI),
    "Tokubetukokko": (NY, NJ, TOKUBETU_SHURUI, SHIKYU_KEITAI),
    "Tokubetukokko_Nendomatu": (NY, NJ, TOKUBETU_SHURUI, SHIKYU_KEITAI),
    "Tokubetukokko_Nendomatu_P": (NY, NJ, TOKUBETU_SHURUI, SHIKYU_KEITAI),
    "SanteiTaishou": (SEIDO_KUBUN, NY, 4),
    "Hiho_Kokunen": (NY,),
    "Sankyu_Taishou": (NY,),
    "Ikukyu_Taishou": (NY,),
    # double Kokko_Wariai[SAISHUNENDO - ( SHONENDO - 1 ) + 1];  107
    "Kokko_Wariai": (SAISHUNENDO - (SHONENDO - 1) + 1,),
    "Tokubetu_Kokko_Wariai": (SAISHUNENDO - (SHONENDO - 1) + 1,
                              TOKUBETU_SHURUI),
    # double Cut_ritu[106][MAX_JUKYU - UNDER_63 + 1];  53
    "Cut_ritu": (NY, MAX_JUKYU - UNDER_63 + 1),
    # double Tumatumi[SEIDO_KUBUN + 1][SAISHUNENDO - TUMATUMI_NENDO + 1];
    "Tumatumi": (SEIDO_KUBUN + 1, SAISHUNENDO - TUMATUMI_NENDO + 1),
    "Tumatumi_2014": (SEIDO_KUBUN + 1,),
    "i_rate_tumatumi": (NY,),

    # ---- mkiso.h ----
    "Hokenryou_m": (NY, 2),
    "Hokenryou_y": (NY,),
    "Fuka_Hokenryou_m": (NY,),
    "Fuka_Hokenryou_y": (NY,),
    "Kodomo_Noufukin": (NY,),
    "Fuka_Ninzu": (NY,),
    "Ichijikin": (NY, 3),
    "Ichijikin_Nendomatu": (NY, 3),
    "Ichijikin_Cut": (NY, 3),
    "Kafu": (NY, 4),
    "Kafu_Nendomatu": (NY, 4),
    "Kafu_Cut": (NY, 4),
    "Fuka": (NY, 4),
    "Fuka_Nendomatu": (NY, 4),
    "Kyoshutukin_Cut": (NY, NJ),
    "Kyoshutukin_Kokko_Cut": (NY, NJ),
    "Tokubetukokko_Cut": (NY, NJ, SHIKYU_KEITAI),
    "Tumitate": (NY,),
    "Fukushi": (NY,),
    "Fukushi_Cut": (NY,),
    "Yuushi_Saiken": (NY,),

    # ---- option.h ----
    # Kasan_Sum はどこからも読まれない（癖 3.）
    "Kasan_Sum": (6, NY, NJ, 3),
    "Kasanmae_Kyufu": (6, NY, NJ, SHINKYU, KYUFU_KUBUN, KYUFU_TAISHOU,
                       SHIKYU_KEITAI),
    "Kasanmae_Kyufu_Nendomatu": (6, NY, NJ, SHINKYU, KYUFU_KUBUN,
                                 KYUFU_TAISHOU, SHIKYU_KEITAI),
    "Kasanmae_Kyufu_Nendomatu_P": (6, NY, NJ, SHINKYU, KYUFU_KUBUN,
                                   KYUFU_TAISHOU, SHIKYU_KEITAI),
}

# int tuki[SAISHUNENDO - SHONENDO + 1];  こちらだけ int
_INT_ARRAYS = {
    "tuki": (NY,),
}

# cntl() が argv から決める設定（mcntl.h・option.h）
_SETTINGS_INT = ("kako", "D_MACRO", "D_M_NENDO", "CARRY", "Kurikoshim",
                 "CUT_KOTEI", "CUT_ONE_SHUTU", "C_NENDO", "S_C_NENDO",
                 "T_NENDO", "T_DOAI", "KAISHI1", "KAISHI2", "MARUME_NENDO",
                 "FUKUSHI_NENDO", "Option", "OPTION_START",
                 "OP_HIKIAGE_KANKAKU", "KOKKONASHI", "TOUGOU")

_SETTINGS_STR = ("HIYOUSYADATA", "KOKUNENDATA", "ECON", "SOTOWAKU",
                 "SOTOWAKU_CUT", "YOBI", "Version", "Version_cut",
                 "Version_tumatumi", "Version_Jurai",
                 "HIYOUSYADATA_Jurai_KAKO", "KOKUNENDATA_Jurai_KAKO")

_SETTINGS_DBL = ("MODEL_PENSION", "MODEL_WAGE")


class Glva:
    """原本のグローバル変数一式。

    大きな配列は初回アクセス時に確保する（`__getattr__`）。C の静的領域と
    同じくゼロ初期化で、寸法は `_ARRAYS` の表そのまま。
    """

    def __init__(self):
        for n in _SETTINGS_INT:
            object.__setattr__(self, n, 0)
        for n in _SETTINGS_STR:
            object.__setattr__(self, n, "")
        for n in _SETTINGS_DBL:
            object.__setattr__(self, n, 0.0)
        # FILE *fp_in[INFILE_NUM] / *fp_out[OUTFILE_NUM]（mfile_open.h）
        object.__setattr__(self, "fp_in", [None] * INFILE_NUM)
        object.__setattr__(self, "fp_out", [None] * OUTFILE_NUM)
        object.__setattr__(self, "infile_name", [""] * INFILE_NUM)
        object.__setattr__(self, "outfile_name", [""] * OUTFILE_NUM)

    def __getattr__(self, name):
        shape = _ARRAYS.get(name)
        if shape is not None:
            a = np.zeros(shape, dtype=np.float64)
            object.__setattr__(self, name, a)
            return a
        shape = _INT_ARRAYS.get(name)
        if shape is not None:
            a = np.zeros(shape, dtype=np.int32)
            object.__setattr__(self, name, a)
            return a
        raise AttributeError(
            f"基礎年金のヘッダに {name} という変数はない（移植漏れの可能性）")

    # ---- 確保済みの配列を調べる（デバッグ用） ----
    def allocated(self):
        out = {}
        for n in list(_ARRAYS) + list(_INT_ARRAYS):
            v = self.__dict__.get(n)
            if v is not None:
                out[n] = v.nbytes
        return out

    def allocated_mb(self):
        return sum(self.allocated().values()) / 1e6


# 原本のグローバルは1組しかないので、モジュール単位で1個持つ。
G = Glva()
