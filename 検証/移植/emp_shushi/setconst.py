# -*- coding: utf-8 -*-
"""
プログラム/厚生年金/収支計算/set.h の忠実移植
==============================================
原本の #define をそのまま写す。名前も値も変えない。

年度の表記は「西暦 − 2000」。STTY=9 は 2009 年度、ENDY=125 は 2125 年度。
配列は [年度 - STTY] のように必ずオフセットを引いて添字にするので、
移植でもその式をそのまま残してある（読み替えの間違いを持ち込まないため）。
"""

SYSPATH = "/suuri/rev2024"

STTY = 9         # 収支計算の開始年度（2009年度）
ENDY = 125       # 同 終了年度（2125年度）

FLKS = 15        # ファイル整合性チェックの対象年度
FLKE = 125

ECSTY = 0        # 経済前提の開始年度（2000年度）
ECEDY = 128      # 同 終了年度（2128年度）

ECXA = 60        # 経済前提で年齢別に持つ下限年齢

MAX_REC_LEN = 19999

XA = 64
XB = 115

# 配列の寸法。原本は [ENDY-STTY+1] のように書いてあるので、その値に名前を
# 付けておく（原本の式はコード中にそのまま残す）。
NY = ENDY - STTY + 1        # 117 年度
NE = ECEDY - ECSTY + 1      # 129 年度
NXE = 116 - ECXA            # 56 歳分（60〜115歳）
NX = 116                    # 0〜115歳


def MAX(a, b):
    """set.h:32 のマクロ。"""
    return a if a > b else b


def MIN(a, b):
    """set.h:33 のマクロ。"""
    return a if a < b else b


def MAX3(a, b, c):
    """set.h:35 のマクロ。"""
    return a if a > MAX(b, c) else MAX(b, c)


def MIN3(a, b, c):
    """set.h:36 のマクロ。"""
    return a if a < MIN(b, c) else MIN(b, c)
