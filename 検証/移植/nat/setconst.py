# -*- coding: utf-8 -*-
"""
国民年金/snaps.h の `#define` の忠実移植
========================================
③国民年金の定数。219 行のうち前半（1〜134行）が `#define`、
後半が関数の宣言。ここは前半だけ。

年度は**西暦そのまま**
----------------------
②（`k` = 西暦 − 2000）や⑤と違って、③は**西暦をそのまま添字に
使わない**。配列は `[SAISHUNENDO - SHONENDO + 1]` の長さで、
`nendo - SHONENDO` を添字にする。

    SHONENDO           2020   配列の先頭（足元の1年前）
    SUIKEISHONENDO     2021   推計の初年度（＝基準年度）
    SAISHUNENDO        2125   最終年度
    → 配列の長さ 106

種別（`shubetu`）
-----------------
| 値 | 中身 |
|---|---|
| 0 | `SHUBETU_SUM` 計 |
| 2 | `OTOKO_1GOU` 第1号・男 |
| 3 | `OTOKO_3GOU` 第3号・男 |
| 5 | `ONNA_1GOU` 第1号・女 |
| 6 | `ONNA_3GOU` 第3号・女 |
| 7 | `SHUBETU_OTOKO` 男の計 |
| 8 | `SHUBETU_ONNA` 女の計 |
| 9 | `SHUBETU_SUM_NENDOKAN` 計（年度間） |

`MAX_SHUBETU` は 7。`main.c` は `shubetu` を 1〜6 で回して
`PerformSiml()` が 2・3・5・6 だけ真を返すので、**1 と 4 は
飛ばす**（第2号は②が推計するので③では計算しない）。

納付区分（`MENJO_JOKYO` = 11）
------------------------------
| 値 | 中身 |
|---|---|
| 1 | `NOUFU` 納付 |
| 2 | `MENJO_3_4` 4分の3免除 |
| 3 | `MENJO_1_2` 半額免除 |
| 4 | `MENJO_1_4` 4分の1免除 |
| 5 | `MENJO_HOUTEI` 法定免除 |
| 6 | `MENJO_SHINSEI` 申請全額免除 |
| 7 | `GAKUSEI` 学生納付特例 |
| 8 | `WAKAMONO` 若年者納付猶予 |
| 9 | `SANKYU` 産前産後免除 |
| 10 | `IKUKYU` 育児期間免除 |

添字 0 は使わない（`MENJO_JOKYO` = 11 は 0〜10 を確保するため）。
`MENJO_DANKAI` = 5 は `struct` の中の `menjo[5][3]` の1つ目で、
免除の段階（全額・4分の3・半額・4分の1・法定＋申請）。
`KOKKO_HIKIAGE` = 3 は国庫負担の割合が変わった3つの期間。
"""

__all__ = [
    "KAKO", "KAKO_J",
    "SHONENDO", "SUIKEISHONENDO", "ECON_SHONENDO", "SOTOWAKU_SHONENDO",
    "LIFETABLE_NENDO", "R_KEINEN_SHONENDO", "R_KEINEN_SAISHUNENDO",
    "I_KEINEN_SHONENDO", "I_KEINEN_SAISHUNENDO",
    "SAISHUNENDO", "SUIKEISAISHUNENDO", "SOTOWAKU_SAISHUNENDO",
    "SHIKKENRITU_MIN", "SHIKKENRITU_MAX", "NENDO_JISSEKI",
    "N_O_NENDO", "HenkouSeinendo", "TINSURA_KAISHI", "TANSHUKU_NENDO",
    "TANSHUKU_HOSEI", "TOKUTEI_NENDO", "TOKUTEI_TUKI",
    "WAKAMONO_HENKO_NENDO", "WAKAMONO_HENKO_RITU",
    "IKUKYU_HENKO_NENDO", "IKUKYU_HENKO_RITU",
    "SUM", "MAX_SHUBETU", "OTOKO_1GOU", "OTOKO_3GOU", "ONNA_1GOU",
    "ONNA_3GOU", "SEIBETU", "OTOKO", "ONNA",
    "MAX_HIHO_NENREI", "MIN_HIHO_NENREI", "MAX_KYOSHUTU_NENREI",
    "MAX_HIHO_KIKAN", "HIHO_NENREI_SUM",
    "MAX_WAKU_NENREI", "MIN_WAKU_NENREI",
    "MIN_ROREI_JUKYU", "MAX_ROREI_JUKYU", "KURI_AGE_SAGE_SHIKYU_KUBUN",
    "MIN_SHOGAI_JUKYU", "MAX_SHOGAI_JUKYU",
    "MIN_IZOKU_TUMA_JUKYU", "MAX_IZOKU_TUMA_JUKYU",
    "MIN_IZOKU_OTTO_JUKYU", "MAX_IZOKU_OTTO_JUKYU",
    "MIN_IZOKU_KO_JUKYU", "MAX_IZOKU_KO_JUKYU",
    "MIN_KAFU_JUKYU", "MAX_KAFU_JUKYU",
    "UNDER_67", "NENREI_SUM", "UNDER_64", "UNDER_63",
    "SHUBETU_SUM", "SHUBETU_OTOKO", "SHUBETU_ONNA",
    "SHUBETU_SUM_NENDOKAN", "KURI_AGE_SAGE_SUM",
    "SANKYU_START", "SANKYU_END",
    "MENJO_JOKYO", "NOUFU_KUBUN", "MENJO_DANKAI",
    "NOUFU", "MENJO_3_4", "MENJO_1_2", "MENJO_1_4", "MENJO_HOUTEI",
    "MENJO_SHINSEI", "GAKUSEI", "WAKAMONO", "SANKYU", "IKUKYU",
    "ZENGAKU", "START", "KOKKO_HIKIAGE", "SHOGAI_TOKYU",
    "BUFFER_MAX", "DATA_MAX", "EPSILON", "SHIBOU_KUBUN",
    "TUINOU_NENSU", "TUINOU_NENSU_KUBUN", "KANENDO_NENSU",
    "KANENDO_NENSU_KUBUN", "KOUNOU_NENSU",
    "OP_MAX_KYOSHUTU_NENREI",
    "INFILE_NUM", "OUTFILE_NUM",
]

# 過去債務推計のファイル名に付ける印（`cntl.c:32,37`）
KAKO = "AK"
KAKO_J = "AJ"

# ---- 年度 ----------------------------------------------------------
SHONENDO = 2020                 # 配列の先頭の年度
SUIKEISHONENDO = 2021           # 推計の初年度（基準年度）
ECON_SHONENDO = 2001            # 経済前提の先頭
SOTOWAKU_SHONENDO = 2021        # 外枠の先頭

LIFETABLE_NENDO = 2020          # 生命表の年度
R_KEINEN_SHONENDO = 2015        # 老齢の経年変化の期間
R_KEINEN_SAISHUNENDO = 2030
I_KEINEN_SHONENDO = 2020        # 遺族の経年変化の期間
I_KEINEN_SAISHUNENDO = 2070

SAISHUNENDO = 2125
SUIKEISAISHUNENDO = 2125
SOTOWAKU_SAISHUNENDO = 2125

SHIKKENRITU_MIN = 2019          # 失権率の経年変化の期間
SHIKKENRITU_MAX = 2070

NENDO_JISSEKI = 2022            # 実績のある最終年度

N_O_NENDO = 1926                # 生年の先頭（大正15年度＝昭和元年度）
HenkouSeinendo = 1941           # 制度が変わる生年
TINSURA_KAISHI = 2021           # 賃金スライドの開始
TANSHUKU_NENDO = 2017           # 受給資格期間が25年→10年になった年度
TANSHUKU_HOSEI = (2. / 3.)      # その年度の補正（原本のまま。2/3）

TOKUTEI_NENDO = 2009            # 特定期間（国庫負担2分の1）の年度
TOKUTEI_TUKI = 4                # 同・月

WAKAMONO_HENKO_NENDO = 2016     # 若年者納付猶予の年齢が 30 → 50 になる年度
WAKAMONO_HENKO_RITU = 0.75

IKUKYU_HENKO_NENDO = 2026       # 育児期間の免除が入る年度
IKUKYU_HENKO_RITU = 0.5

# ---- 種別 ----------------------------------------------------------
SUM = 0
MAX_SHUBETU = 7
OTOKO_1GOU = 2
OTOKO_3GOU = 3
ONNA_1GOU = 5
ONNA_3GOU = 6

SEIBETU = 3
OTOKO = 1
ONNA = 2

SHUBETU_SUM = 0
SHUBETU_OTOKO = 7
SHUBETU_ONNA = 8
SHUBETU_SUM_NENDOKAN = 9

# ---- 年齢 ----------------------------------------------------------
MAX_HIHO_NENREI = 70
MIN_HIHO_NENREI = 20
MAX_KYOSHUTU_NENREI = 60

MAX_HIHO_KIKAN = (MAX_HIHO_NENREI - MIN_HIHO_NENREI)      # 50
HIHO_NENREI_SUM = (MAX_HIHO_NENREI + 1 - MIN_HIHO_NENREI)  # 51

MAX_WAKU_NENREI = 100
MIN_WAKU_NENREI = 15

MIN_ROREI_JUKYU = 60
MAX_ROREI_JUKYU = 115
KURI_AGE_SAGE_SHIKYU_KUBUN = (70 - 60 + 1)                 # 11
KURI_AGE_SAGE_SUM = KURI_AGE_SAGE_SHIKYU_KUBUN

MIN_SHOGAI_JUKYU = 20
MAX_SHOGAI_JUKYU = 115

MIN_IZOKU_TUMA_JUKYU = 16
MAX_IZOKU_TUMA_JUKYU = 115

MIN_IZOKU_OTTO_JUKYU = 18
MAX_IZOKU_OTTO_JUKYU = 115

MIN_IZOKU_KO_JUKYU = 0
MAX_IZOKU_KO_JUKYU = 19

MIN_KAFU_JUKYU = 26
MAX_KAFU_JUKYU = 64

UNDER_67 = 67
NENREI_SUM = 62
UNDER_64 = 64
UNDER_63 = 63

SANKYU_START = 15               # 産前産後免除の年齢
SANKYU_END = 49

# ---- 納付・免除 ----------------------------------------------------
MENJO_JOKYO = 11                # 納付区分の数（添字 0 は使わない）
NOUFU_KUBUN = 5
MENJO_DANKAI = 5                # `struct` の `menjo[5][3]` の1つ目
NOUFU = 1
MENJO_3_4 = 2
MENJO_1_2 = 3
MENJO_1_4 = 4
MENJO_HOUTEI = 5
MENJO_SHINSEI = 6
GAKUSEI = 7
WAKAMONO = 8
SANKYU = 9
IKUKYU = 10
ZENGAKU = 1
START = 1

KOKKO_HIKIAGE = 3               # 国庫負担の割合が変わった3つの期間
SHOGAI_TOKYU = 3                # 障害等級（1級・2級・3級）

# ---- 入出力 --------------------------------------------------------
BUFFER_MAX = 1000
DATA_MAX = 120
EPSILON = 1.e-14

SHIBOU_KUBUN = 7                # 死亡一時金の区分

TUINOU_NENSU = 10               # 追納できる年数
TUINOU_NENSU_KUBUN = 3
KANENDO_NENSU = 2               # 過年度納付
KANENDO_NENSU_KUBUN = 3
KOUNOU_NENSU = 10               # 後納

# `option.h` の1つ（`snaps.h` ではない）
OP_MAX_KYOSHUTU_NENREI = 65     # 45年化のときの拠出年齢の上限

# `mfile_open.h` の2つ
INFILE_NUM = 86
OUTFILE_NUM = 11
