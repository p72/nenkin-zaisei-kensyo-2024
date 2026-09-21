# -*- coding: utf-8 -*-
"""
基礎年金/file_write_kakyu.c の忠実移植（⑤収支計算へ渡す拠出金ファイル）
=========================================================================
`KYOSHUTUKIN{Version}-{YOBI}` を書く。⑤厚生年金収支計算がこれを読んで
各制度の基礎年金拠出金を負担する。④の出力でいちばん大きい（7.4MB）。

書式
----
    shikyu_keitai:1                       ← 基本／加給の区切り
    年度,制度,種別,62歳,63歳,…,115歳     ← 54 列

    種別 1  拠出金（年度末値・翌年度の被保険者数で割った方）
    種別 2  拠出金（年度末値）
    種別 3  拠出金の国庫負担分（年度末値・翌年度割）
    種別 4  拠出金の国庫負担分（年度末値）

「制度」の番号がずれる
----------------------
    0  厚年      `Kyoshutukin_Nendomatu[KOUNEN]`
    1  国共      `Kyoshutukin_Nendomatu[KOKKYO]`
    2  （空）    ぜんぶ 0
    3  （空）    ぜんぶ 0
    4  地共      `Kyoshutukin_Nendomatu[CHIKYO]`
    5  私学      `Kyoshutukin_Nendomatu[SHIGAKU]`
    6  （空）    ぜんぶ 0
    7  国年      `TOUGOU == 1` のときだけ
    8  特別国庫  `TOUGOU == 1` のときだけ

原本は `seido = 2〜3` を `seido - 2`（0・1）、`seido = 6〜7` を
`seido - 4`（2・3）、`seido = 4〜5` を `seido` そのまま（4・5）と、
**3通りの引き算**で番号を作っている。2・3・6 が空なのは⑤側の
読み込みの都合（制度の並びを合わせるための穴）。

年度の範囲が種別で1年ずれる
---------------------------
種別 1・3（翌年度割）は 2010〜2020年度が 0 で 2021年度から実データ、
種別 2・4 は 2010〜2019年度が 0 で 2020年度から実データ。
翌年度割は「前年度の `_P`」を読むので1年後ろにずれる。

原本の癖をそのまま残しているところ
----------------------------------
1. **同じ8ブロックが3回、ほぼ丸ごと重複している**（`seido = 2〜3`、
   `6〜7`、`CHIKYO〜SHIGAKU`）。さらに制度 6 のぶんが展開されていて、
   580 行のうち実質は 30 行ぶん。（`検証/原本の不具合.md`）

2. **`seido = 6〜7` のブロックが `sotai_nendo` を計算するだけで使わない。**
   出すのは 0 だけなのに `sotai_nendo = nendo - SHONENDO` を毎行やる。

3. **制度 8（特別国庫）の種別 1 と 3 が同じ値を出す**
   （`file_write_kakyu.c:498,544` がどちらも
   `Tokubetukokko_Nendomatu_P[...][SUM][...]`）。種別 3 は
   「国庫負担分」のはずだが、特別国庫は全額国庫なので同じになる。

4. **`%20.14le` の `l` は `double` では無視される。**`%20.14e` と同じ。
"""
from glva import G
from setconst import (
    CHIKYO, KAKYU, KIHON, KOKKYO, KOKUNEN, KOUNEN, KYOSHUTUKIN, MAX_JUKYU,
    NENREI_SUM, SAISHUNENDO, SHIGAKU, SHONENDO, SUIKEISHONENDO, SUM,
)
from cnum import asctime_now

__all__ = ["file_write_kakyu"]

_NJ = MAX_JUKYU - NENREI_SUM + 1                 # 54 列

# ぜんぶ 0 の行の中身（`%20.14le` を 54 個）。ほとんどの行がこれなので
# 毎回組み立てずに使い回す
_ZEROS = ("%20.14e," % 0.) * (_NJ - 1) + ("%20.14e\n" % 0.)


def _row(w, nendo, seido_out, kubun, vals):
    """1行ぶん（`年度,制度,種別` ＋ 54 列）。"""
    w("%d,%d,%d," % (nendo - 2000, seido_out, kubun))
    if vals is None:
        w(_ZEROS)
        return
    for k in range(0, _NJ - 1):
        w("%20.14e," % vals[k])
    w("%20.14e\n" % vals[_NJ - 1])


def _block(w, seido_out, kubun, arr, seido, shift):
    """種別1つぶん。`shift` が 1 なら翌年度割（前年度の `_P` を読む）。

    `arr` が None ならぜんぶ 0。
    """
    # 実データが始まる前の年度は 0
    zero_end = SUIKEISHONENDO if shift else SUIKEISHONENDO - 1
    for nendo in range(2010, zero_end + 1):
        _row(w, nendo, seido_out, kubun, None)

    for nendo in range(zero_end + 1, SAISHUNENDO + 1):
        sn = nendo - SHONENDO - shift
        _row(w, nendo, seido_out, kubun,
             None if arr is None else arr[seido][sn])


def file_write_kakyu():
    """file_write_kakyu.c:12 の忠実移植。"""
    fp = G.fp_out[KYOSHUTUKIN]
    w = fp.write

    # write_BeginData（`stdfm.c:160`）。**時刻が入る**
    w(asctime_now())
    w("#99-0000-0000\n")

    for shikyu_keitai in range(KIHON, KAKYU + 1):
        w("shikyu_keitai:%d\n" % shikyu_keitai)

        kn = G.Kyoshutukin_Nendomatu[:, :, :, shikyu_keitai]
        knP = G.Kyoshutukin_Nendomatu_P[:, :, :, shikyu_keitai]
        kk = G.Kyoshutukin_Kokko_Nendomatu[:, :, :, shikyu_keitai]
        kkP = G.Kyoshutukin_Kokko_Nendomatu_P[:, :, :, shikyu_keitai]

        # ---- 制度 0・1（厚年・国共） ----
        for seido in range(KOUNEN, KOKKYO + 1):
            out = seido - 2
            _block(w, out, 1, knP, seido, 1)
            _block(w, out, 2, kn, seido, 0)
            _block(w, out, 3, kkP, seido, 1)
            _block(w, out, 4, kk, seido, 0)

        # ---- 制度 2・3（穴。ぜんぶ 0。癖 2.） ----
        for seido in range(6, 8):
            out = seido - 4
            _block(w, out, 1, None, seido, 1)
            _block(w, out, 2, None, seido, 0)
            _block(w, out, 3, None, seido, 1)
            _block(w, out, 4, None, seido, 0)

        # ---- 制度 4・5（地共・私学） ----
        for seido in range(CHIKYO, SHIGAKU + 1):
            out = seido
            _block(w, out, 1, knP, seido, 1)
            _block(w, out, 2, kn, seido, 0)
            _block(w, out, 3, kkP, seido, 1)
            _block(w, out, 4, kk, seido, 0)

        # ---- 制度 6（穴） ----
        _block(w, 6, 1, None, 0, 1)
        _block(w, 6, 2, None, 0, 0)
        _block(w, 6, 3, None, 0, 1)
        _block(w, 6, 4, None, 0, 0)

        if G.TOUGOU == 1:
            # ---- 制度 7（国年） ----
            _block(w, 7, 1, knP, KOKUNEN, 1)
            _block(w, 7, 2, kn, KOKUNEN, 0)
            _block(w, 7, 3, kkP, KOKUNEN, 1)
            _block(w, 7, 4, kk, KOKUNEN, 0)

            # ---- 制度 8（特別国庫。癖 3. 種別 1 と 3 が同じ） ----
            tkP = G.Tokubetukokko_Nendomatu_P[:, :, SUM, shikyu_keitai]
            tk = G.Tokubetukokko_Nendomatu[:, :, SUM, shikyu_keitai]
            _block(w, 8, 1, [tkP], 0, 1)
            _block(w, 8, 2, [tk], 0, 0)
            _block(w, 8, 3, [tkP], 0, 1)
            _block(w, 8, 4, [tk], 0, 0)

    fp.close()
    G.fp_out[KYOSHUTUKIN] = None

    return
