# -*- coding: utf-8 -*-
"""
基礎年金/Atamawari.c の忠実移植（基礎年金給付費と拠出金の頭割り）
===================================================================
④の心臓。③④が読んだ受給者数から給付費を組み立て、年度末値を年度間値に
直し、被保険者数で頭割りして各制度の基礎年金拠出金を出す。
`main.c` から**2回**呼ばれる（マクロ経済スライドの調整前と調整後）。

段取り
------
1. `clear_*`   27本の配列を 0 で埋める
2. `cal_kyufu_nendomatu`         年度末の給付費（性別2回足し込む）
   `cal_tokubetukokko_nendonmatu` 年度末の特別国庫負担
3. `Cut_ritu` を掛ける（加給は63歳の率、それ以外は年齢別の率）
   そのついでに国庫負担分 `Kokko_Nendomatu` を作る
4. `cal_sum_*`  制度計・年齢計・新旧計・区分計・対象計・形態計を足す
5. `cal_*_nendokan`  年度末値2つ（前年度の1歳下と当年度）から年度間値
6. `cal_sum_*` をもう一度（年度間値に対して）
7. 単価 `Tanka` と拠出金 `Kyoshutukin` を頭割りで作る

`Kyufu` と `Kasanmae_Kyufu` の違い
----------------------------------
`cal_kyufu_nendomatu` には**まったく同じ引数**で2回呼ばれるので、
この時点では中身も同じ。違いが出るのは③国民年金・②厚生年金の側で
振替加算を足すかどうかで、④の中では
**`Kokko_Nendomatu` を作るのに `Kasanmae_` を使う**ところだけ。
どちらも同じ値なので結果は変わらない。（`検証/原本の不具合.md`）

年度間値の作り方（`cal_kyufu_nendokan`）
----------------------------------------
    年度間値 = 前年度末（1歳下）× ( 2 + 6 × 改定率 ) / 12
             + 当年度末          × ( 6 − 2 ) / 12

支払遅れ2か月ぶんを前年度から持ってくる。`nenrei == UNDER_64`（64歳）
だけは当年度末の 63 歳と 64 歳を**両方**足す（63歳で新規に出た人を
64歳の年度間値に含めるため）。

改定率は 67 歳以下と加給は 67 歳の率、68 歳以上の基本は年齢別の率。

`cal_sum_*` の足し方（原本の二重ループの意味）
-----------------------------------------------
`cal_sum_kyufu` は6つの軸（制度・年齢・新旧・区分・対象・形態）それぞれに
ついて「その軸を計（添字 0）にまとめるか、元の値のままか」の 2^6 = 64
通りを回し、元の値を足し込む。つまり**64 通りの周辺和**を一度に作る。

```c
if( seido[1]==1 && shinkyu[1]==1 && kubun[1]==1 &&
    taishou[1]==1 && shikyu_keitai[1]==1 ) continue ;
```

で飛ばすのは「年齢以外すべて元の値のまま」の2通り。うち1つは
自分自身に足す（二重計上）なので飛ばすのが正しいが、**もう1つ
（年齢だけ計にまとめる）も一緒に飛んでいる**。その結果
`Kyufu[制度][年度][年齢計][新旧][区分][対象][形態]` が
**すべて 0 のまま**になる。出力（`printout`）が読むのは
`[制度][年度][年齢計][新旧][区分][計][計]` なので 0 にはならず、
出力には出ない。（`検証/原本の不具合.md`）

移植版は周辺和として計算する。足す順番は原本と同じ「元の値の添字を
C の行優先で回る順」なので、`np.add.accumulate` で1ビットも変わらない
（`検証/移植/README.md` の「足し算の順番」を参照）。

原本の癖をそのまま残しているところ
----------------------------------
1. **`Atamawari()` が宣言だけして使わない変数を7つ持つ**
   （`nenrei` 以外の `seido` `shinkyu` `kubun` `taishou` は使うが、
   `noufu_joutai` は使わない）。

2. **`Tanka_Kokko_Nendomatu_P` の最終年度だけ `Kokko_Nendomatu` を
   読む**（`Atamawari.c:407`）。他の年度は `Kokko_Nendomatu_P`。
   `_P` は「翌年度の被保険者数で割る」ぶんなので、最終年度に
   `_P` が無いための処理だが、分子も `_P` でなくしてしまっている。
   `Kyufu` 側（`Atamawari.c:403`）は `Kyufu_Nendomatu_P` のままなので
   揃っていない。（`検証/原本の不具合.md`）

3. **`Kyoshutukin_Nendomatu` は制度計（添字 0）を作らない。**
   `seido = KOKUNEN` から回るので `[0]` は 0 のまま。
   `Kyoshutukin`（年度間値）は `seido = SUM` から回るので作る。

4. **`cal_sum_kyufu` の引数が配列の寸法を書き下している。**
   C では配列の先頭の次元は無視されるので、`[SEIDO_KUBUN]` と
   `[6]`（`Kasanmae_Kyufu`）の違いは効かない。
"""
import numpy as np

from glva import G
from setconst import (
    ECON_SHONENDO, GONEN, HATACHIMAE, IPPAN, IZOKU, KAKYU, KAKYU_NOUFU,
    KASAMENJO, KASANOUFU, KIHON, KOKUNEN, KOUNEN, KYOSHUTU, MAX_JUKYU,
    MENJO, MENJO_KOUHAN, MENJO_ZENHAN, NENREI_SUM, NEW, NOUFU, OLD, ONNA,
    OTOKO, ROFUKU_SHITASASAE, ROREI, SAISHUNENDO, SHIGAKU, SHOGAI,
    SHONENDO, SUIKEISAISHUNENDO, SUM, TOKUBETU, TOKUBETU_20MAE,
    TOKUBETU_GONEN, TOKUBETU_KASAAGE, TOKUBETU_KASAMENJO, TOKUBETU_MENJO,
    TOKUBETU_SHITASASAE, UNDER_63, UNDER_64, UNDER_67,
)

__all__ = ["Atamawari"]

SHIHARAIOKURE = 2

# 年齢の添字。給付費の配列は `nenrei - NENREI_SUM`
_J63 = UNDER_63 - NENREI_SUM                    # 1
_J64 = UNDER_64 - NENREI_SUM                    # 2
_JEND = MAX_JUKYU - NENREI_SUM + 1              # 54

# 実データが入る添字の範囲（`cal_sum_*` の「元の値」の範囲）
_S_SEIDO = slice(KOKUNEN, SHIGAKU + 1)          # 1〜5
_S_NENREI = slice(_J63, _JEND)                  # 1〜53
_S_SHINKYU = slice(NEW, OLD + 1)                # 1〜2
_S_KUBUN = slice(ROREI, IZOKU + 1)              # 1〜3
_S_TAISHOU = slice(KYOSHUTU, TOKUBETU + 1)      # 1〜2
_S_KEITAI = slice(KIHON, KAKYU + 1)             # 1〜2
_S_SHURUI = slice(TOKUBETU_MENJO, TOKUBETU_20MAE + 1)   # 1〜6

# `cal_sum_*` が回る軸の並び（`_marginal` に渡す添字）
_SUM_KYUFU = (_S_SEIDO, _S_NENREI, _S_SHINKYU, _S_KUBUN, _S_TAISHOU,
              _S_KEITAI)
_SUM_KOKKO = (_S_SEIDO, _S_NENREI, _S_SHINKYU, _S_KUBUN, _S_KEITAI)
_SUM_TOKUBETU = (_S_NENREI, _S_SHURUI, _S_KEITAI)


def _subsets(n, keep):
    """「どの軸を計（添字 0）にまとめるか」の組み合わせを原本の順に並べる。

    `keep` は「この軸だけが計に入っても飛ばす」軸の集合（原本の
    `continue` の条件）。原本は `seido[1]`〜`shikyu_keitai[1]` が
    すべて 1（＝元の値のまま）のときだけ飛ばすので、まとめる軸の集合が
    `keep` の部分集合になる組み合わせが落ちる。
    """
    out = []
    for mask in range(1 << n):
        S = frozenset(a for a in range(n) if mask >> a & 1)
        if S <= keep:
            continue
        out.append(S)
    return out


# 飛ばすのは「年齢以外すべて元の値のまま」の2通り（年齢を計にまとめる方も
# 一緒に落ちる。上の解説を参照）
_SUBS_KYUFU = _subsets(6, frozenset({1}))
_SUBS_KOKKO = _subsets(5, frozenset({1}))
_SUBS_TOKUBETU = _subsets(3, frozenset({0}))


def _marginal(src, axes):
    """`src` の `axes` 軸を、原本と同じ順（C の行優先）で逐次に足す。

    `axes` の軸を昇順に前へ出してから1本にまとめ、`np.add.accumulate`
    の最後の要素を取る。`np.sum` は対和（pairwise）で順番が違うので
    使えない。残りの軸については要素ごとの演算なので、原本の
    「元の値の添字を行優先で回って足し込む」と1ビットも変わらない。
    """
    ax = tuple(sorted(axes))
    rest = tuple(a for a in range(src.ndim) if a not in axes)
    x = np.ascontiguousarray(np.transpose(src, ax + rest))
    x = x.reshape((-1,) + tuple(src.shape[a] for a in rest))
    return np.add.accumulate(x, axis=0)[-1]


def _cal_sum(B, slices, subsets):
    """`cal_sum_kyufu` / `cal_sum_kokko` / `cal_sum_tokubetukokko` の中身。

    `B` は年度の軸を落とした眺め（`A[:, sn]` など）、`slices` は
    「元の値」の添字の範囲。

    **足し込み先が 0 であることを前提にしている。**原本は
    `dest += src_1 ; dest += src_2 ; …` と足すので、`dest` に値が
    残っていれば `((dest + s1) + s2) + …` になる。こちらは
    `dest + ((s1 + s2) + …)` なので、`dest != 0` なら1ビット変わりうる。

    この前提が成り立つ理由。足し込み先は必ず添字 0 を1つ以上含み
    （`_subsets` が落とす2通りを除いてある）、`clear_*` のあとに
    0 以外を書くのは `_cal_kyufu_nendomatu` / `_apply_cut_ritu` /
    `_cal_*_nendokan` だけで、どれも添字 0 に書かない。`Atamawari()` は
    2回呼ばれるが、毎回頭で全部 0 にする。

    確かめているのは出力のバイト一致（6通りの設定で7ファイル）と
    `test_kiso_num.py` の `test_周辺和が原本のループと1ビットも違わない`。
    """
    src = B[slices]
    for S in subsets:
        dest = tuple(slice(0, 1) if a in S else slices[a]
                     for a in range(len(slices)))
        view = B[dest]
        view += _marginal(src, S).reshape(view.shape)


def Atamawari():
    """Atamawari.c:97 の忠実移植。"""
    # ---- 1. clear_* ----
    for name in ("Kyufu", "Kyufu_Nendomatu", "Kyufu_Nendomatu_P",
                 "Kasanmae_Kyufu", "Kasanmae_Kyufu_Nendomatu",
                 "Kasanmae_Kyufu_Nendomatu_P",
                 "Kokko", "Kokko_Nendomatu", "Kokko_Nendomatu_P",
                 "Kyoshutukin", "Kyoshutukin_Nendomatu",
                 "Kyoshutukin_Nendomatu_P",
                 "Kyoshutukin_Kokko", "Kyoshutukin_Kokko_Nendomatu",
                 "Kyoshutukin_Kokko_Nendomatu_P",
                 "Tanka", "Tanka_Nendomatu", "Tanka_Nendomatu_P",
                 "Tanka_Kokko", "Tanka_Kokko_Nendomatu",
                 "Tanka_Kokko_Nendomatu_P",
                 "Tokubetukokko", "Tokubetukokko_Nendomatu",
                 "Tokubetukokko_Nendomatu_P"):
        getattr(G, name)[...] = 0.0

    # ---- 2〜4. 年度末値 ----
    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        sn = nendo - SHONENDO

        for seibetu in range(OTOKO, ONNA + 1):
            _cal_kyufu_nendomatu(nendo, seibetu, 0, G.Kyufu_Nendomatu)
            _cal_kyufu_nendomatu(nendo, seibetu, 0,
                                 G.Kasanmae_Kyufu_Nendomatu)
            _cal_tokubetukokko_nendonmatu(nendo, seibetu, 0,
                                          G.Tokubetukokko_Nendomatu)
            _cal_kyufu_nendomatu(nendo, seibetu, 1, G.Kyufu_Nendomatu_P)
            _cal_kyufu_nendomatu(nendo, seibetu, 1,
                                 G.Kasanmae_Kyufu_Nendomatu_P)
            _cal_tokubetukokko_nendonmatu(nendo, seibetu, 1,
                                          G.Tokubetukokko_Nendomatu_P)

        _apply_cut_ritu(nendo)

        for A in (G.Kyufu_Nendomatu, G.Kyufu_Nendomatu_P,
                  G.Kasanmae_Kyufu_Nendomatu,
                  G.Kasanmae_Kyufu_Nendomatu_P):
            _cal_sum(A[:, sn], _SUM_KYUFU, _SUBS_KYUFU)
        for A in (G.Kokko_Nendomatu, G.Kokko_Nendomatu_P):
            _cal_sum(A[:, sn], _SUM_KOKKO, _SUBS_KOKKO)
        for A in (G.Tokubetukokko_Nendomatu, G.Tokubetukokko_Nendomatu_P):
            _cal_sum(A[sn], _SUM_TOKUBETU, _SUBS_TOKUBETU)

    # ---- 5. 年度間値 ----
    for nendo in range(SHONENDO + 1, SAISHUNENDO + 1):
        for nenrei in range(UNDER_64, MAX_JUKYU + 1):
            _cal_kyufu_nendokan(nendo, nenrei, SHIHARAIOKURE,
                                G.Kasanmae_Kyufu,
                                G.Kasanmae_Kyufu_Nendomatu,
                                G.Kasanmae_Kyufu_Nendomatu_P)
            _cal_kyufu_nendokan(nendo, nenrei, SHIHARAIOKURE, G.Kyufu,
                                G.Kyufu_Nendomatu, G.Kyufu_Nendomatu_P)
            _cal_kokko_nendokan(nendo, nenrei, SHIHARAIOKURE, G.Kokko,
                                G.Kokko_Nendomatu, G.Kokko_Nendomatu_P)
            _cal_tokubetukokko_nendokan(nendo, nenrei, SHIHARAIOKURE,
                                        G.Tokubetukokko,
                                        G.Tokubetukokko_Nendomatu,
                                        G.Tokubetukokko_Nendomatu_P)

    # ---- 6. 年度間値の計 ----
    for nendo in range(SHONENDO + 1, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        for A in (G.Kyufu, G.Kasanmae_Kyufu):
            _cal_sum(A[:, sn], _SUM_KYUFU, _SUBS_KYUFU)
        _cal_sum(G.Kokko[:, sn], _SUM_KOKKO, _SUBS_KOKKO)
        _cal_sum(G.Tokubetukokko[sn], _SUM_TOKUBETU, _SUBS_TOKUBETU)

    # ---- 7. 単価と拠出金 ----
    for nendo in range(SHONENDO + 1, SUIKEISAISHUNENDO + 1):
        _tanka_kyoshutukin(nendo)

    return


# ---------------------------------------------------------------------------
# 2. 年度末の給付費
# ---------------------------------------------------------------------------
def _cal_kyufu_nendomatu(nendo, seibetu, P, kn):
    """Atamawari.c:649 の忠実移植。**年齢の軸をまとめて処理する。**

    原本は `nenrei` ごとに呼ばれるが、中身は年齢に依らない同じ式なので
    年齢の軸をベクトルで回しても要素ごとの演算で1ビットも変わらない。
    性別は原本どおり2回に分けて足す（足す順番が変わらないように）。
    """
    sn = nendo - SHONENDO
    J = _S_NENREI
    p = 1 if (nendo != SAISHUNENDO and P == 1) else 0
    tkw = G.Tokubetu_Kokko_Wariai[nendo + p - (SHONENDO - 1)]

    rn = G.Rorei_New
    sg = G.Shogai_New
    iz = G.Izoku_New
    ro = G.Rorei_Old
    so = G.Shogai_Old
    zo = G.Izoku_Old
    fk = G.FurikaeKasan

    # ---- 国年 ----
    kn[KOKUNEN, sn, J, NEW, ROREI, KYOSHUTU, KIHON] += \
        rn[KOKUNEN, sn, J, seibetu, NOUFU]

    kn[KOKUNEN, sn, J, OLD, ROREI, KYOSHUTU, KIHON] += (
        ro[KOKUNEN, sn, J, seibetu, NOUFU]
        + ro[KOKUNEN, sn, J, seibetu, KASANOUFU]
        * (1. - tkw[TOKUBETU_KASAAGE])
        + ro[KOKUNEN, sn, J, seibetu, GONEN]
        * (1. - tkw[TOKUBETU_GONEN]))

    for noufu_joutai in range(MENJO_ZENHAN, MENJO_KOUHAN + 1):
        kn[KOKUNEN, sn, J, NEW, ROREI, TOKUBETU, KIHON] += \
            rn[KOKUNEN, sn, J, seibetu, noufu_joutai]

    kn[KOKUNEN, sn, J, OLD, ROREI, TOKUBETU, KIHON] += (
        ro[KOKUNEN, sn, J, seibetu, MENJO] * tkw[TOKUBETU_MENJO]
        + ro[KOKUNEN, sn, J, seibetu, KASANOUFU] * tkw[TOKUBETU_KASAAGE]
        + ro[KOKUNEN, sn, J, seibetu, KASAMENJO] * tkw[TOKUBETU_KASAMENJO]
        + ro[KOKUNEN, sn, J, seibetu, ROFUKU_SHITASASAE]
        * tkw[TOKUBETU_SHITASASAE]
        + ro[KOKUNEN, sn, J, seibetu, GONEN] * tkw[TOKUBETU_GONEN])

    for k in range(KIHON, KAKYU + 1):
        kn[KOKUNEN, sn, J, NEW, SHOGAI, KYOSHUTU, k] += (
            sg[KOKUNEN, sn, J, seibetu, IPPAN, k]
            + sg[KOKUNEN, sn, J, seibetu, HATACHIMAE, k]
            * (1. - tkw[TOKUBETU_20MAE]))

        kn[KOKUNEN, sn, J, OLD, SHOGAI, KYOSHUTU, k] += \
            so[KOKUNEN, sn, J, seibetu, k, NOUFU]

        kn[KOKUNEN, sn, J, NEW, SHOGAI, TOKUBETU, k] += \
            sg[KOKUNEN, sn, J, seibetu, HATACHIMAE, k] * tkw[TOKUBETU_20MAE]

        kn[KOKUNEN, sn, J, OLD, SHOGAI, TOKUBETU, k] += \
            so[KOKUNEN, sn, J, seibetu, k, MENJO] * tkw[TOKUBETU_MENJO]

        kn[KOKUNEN, sn, J, NEW, IZOKU, KYOSHUTU, k] += \
            iz[KOKUNEN, sn, J, seibetu, k]

        kn[KOKUNEN, sn, J, OLD, IZOKU, KYOSHUTU, k] += \
            zo[KOKUNEN, sn, J, seibetu, k, NOUFU]

        kn[KOKUNEN, sn, J, OLD, IZOKU, TOKUBETU, k] += \
            zo[KOKUNEN, sn, J, seibetu, k, MENJO] * tkw[TOKUBETU_MENJO]

    # ---- 被用者年金（厚年・国共・地共・私学） ----
    for seido in range(KOUNEN, SHIGAKU + 1):
        kn[seido, sn, J, NEW, ROREI, KYOSHUTU, KIHON] += \
            rn[seido, sn, J, seibetu, NOUFU]

        kn[seido, sn, J, OLD, ROREI, KYOSHUTU, KIHON] += (
            ro[seido, sn, J, seibetu, NOUFU]
            + ro[seido, sn, J, seibetu, KASANOUFU]
            + ro[seido, sn, J, seibetu, GONEN])

        kn[seido, sn, J, OLD, ROREI, KYOSHUTU, KAKYU] += \
            ro[seido, sn, J, seibetu, KAKYU_NOUFU]

        for k in range(KIHON, KAKYU + 1):
            kn[seido, sn, J, NEW, SHOGAI, KYOSHUTU, k] += (
                sg[seido, sn, J, seibetu, IPPAN, k]
                + sg[seido, sn, J, seibetu, HATACHIMAE, k])

            kn[seido, sn, J, OLD, SHOGAI, KYOSHUTU, k] += \
                so[seido, sn, J, seibetu, k, NOUFU]

            kn[seido, sn, J, NEW, IZOKU, KYOSHUTU, k] += \
                iz[seido, sn, J, seibetu, k]

            kn[seido, sn, J, OLD, IZOKU, KYOSHUTU, k] += \
                zo[seido, sn, J, seibetu, k, NOUFU]

    # ---- 振替加算は全制度ぶんを国年に寄せる ----
    for seido in range(KOKUNEN, SHIGAKU + 1):
        kn[KOKUNEN, sn, J, NEW, ROREI, KYOSHUTU, KIHON] += \
            fk[seido, sn, J, seibetu, ROREI]

        kn[KOKUNEN, sn, J, NEW, SHOGAI, KYOSHUTU, KIHON] += \
            fk[seido, sn, J, seibetu, SHOGAI]


def _cal_tokubetukokko_nendonmatu(nendo, seibetu, P, tk):
    """Atamawari.c:781 の忠実移植。年齢の軸をまとめて処理する。"""
    sn = nendo - SHONENDO
    J = _S_NENREI
    p = 1 if (nendo != SAISHUNENDO and P == 1) else 0
    tkw = G.Tokubetu_Kokko_Wariai[nendo + p - (SHONENDO - 1)]

    rn = G.Rorei_New
    sg = G.Shogai_New
    ro = G.Rorei_Old
    so = G.Shogai_Old
    zo = G.Izoku_Old

    for noufu_joutai in range(MENJO_ZENHAN, MENJO_KOUHAN + 1):
        tk[sn, J, TOKUBETU_MENJO, KIHON] += \
            rn[KOKUNEN, sn, J, seibetu, noufu_joutai]

    tk[sn, J, TOKUBETU_MENJO, KIHON] += \
        ro[KOKUNEN, sn, J, seibetu, MENJO] * tkw[TOKUBETU_MENJO]

    # 嵩上げ（納付）・嵩上げ（免除）・老福下支え・５年年金。旧法老齢の
    # 添字は「特別国庫の種類 + 3」（KASANOUFU=5 ↔ TOKUBETU_KASAAGE=2）
    for shurui in range(TOKUBETU_KASAAGE, TOKUBETU_GONEN + 1):
        tk[sn, J, shurui, KIHON] += \
            ro[KOKUNEN, sn, J, seibetu, shurui + 3] * tkw[shurui]

    for k in range(KIHON, KAKYU + 1):
        tk[sn, J, TOKUBETU_20MAE, k] += \
            sg[KOKUNEN, sn, J, seibetu, HATACHIMAE, k] * tkw[TOKUBETU_20MAE]

        tk[sn, J, TOKUBETU_MENJO, k] += \
            so[KOKUNEN, sn, J, seibetu, k, MENJO] * tkw[TOKUBETU_MENJO]

        tk[sn, J, TOKUBETU_MENJO, k] += \
            zo[KOKUNEN, sn, J, seibetu, k, MENJO] * tkw[TOKUBETU_MENJO]


# ---------------------------------------------------------------------------
# 3. Cut_ritu を掛けて国庫負担分を作る
# ---------------------------------------------------------------------------
def _apply_cut_ritu(nendo):
    """Atamawari.c:180-272。年齢の軸などをまとめて処理する。

    加給（`KAKYU`）は 63 歳の率、それ以外は年齢別の率を掛ける。
    原本は `taishou == KYOSHUTU` の枝で `Kokko_Nendomatu` を作るが、
    そのときには `Kasanmae_Kyufu_Nendomatu` に率が掛かり終わっている
    ので、率を掛けたあとに国庫負担分を作るのと同じ。
    """
    sn = nendo - SHONENDO
    # `Cut_ritu` は `nenrei - UNDER_63` で引く。63〜115歳ぶん
    c_kihon = G.Cut_ritu[sn, 0:MAX_JUKYU - UNDER_63 + 1]
    c_kakyu = G.Cut_ritu[sn, UNDER_63 - UNDER_63]
    # ブロードキャスト用。軸は (seido, nenrei, shinkyu, kubun, taishou)
    ck = c_kihon.reshape(-1, 1, 1, 1)

    for A in (G.Kasanmae_Kyufu_Nendomatu, G.Kasanmae_Kyufu_Nendomatu_P,
              G.Kyufu_Nendomatu, G.Kyufu_Nendomatu_P):
        A[_S_SEIDO, sn, _S_NENREI, _S_SHINKYU, _S_KUBUN, _S_TAISHOU,
          KAKYU] *= c_kakyu
        A[_S_SEIDO, sn, _S_NENREI, _S_SHINKYU, _S_KUBUN, _S_TAISHOU,
          KIHON] *= ck

    kw = G.Kokko_Wariai[nendo - (SHONENDO - 1)]
    G.Kokko_Nendomatu[_S_SEIDO, sn, _S_NENREI, _S_SHINKYU, _S_KUBUN,
                      _S_KEITAI] = (
        G.Kasanmae_Kyufu_Nendomatu[_S_SEIDO, sn, _S_NENREI, _S_SHINKYU,
                                   _S_KUBUN, KYOSHUTU, _S_KEITAI] * kw)
    G.Kokko_Nendomatu_P[_S_SEIDO, sn, _S_NENREI, _S_SHINKYU, _S_KUBUN,
                        _S_KEITAI] = (
        G.Kasanmae_Kyufu_Nendomatu_P[_S_SEIDO, sn, _S_NENREI, _S_SHINKYU,
                                     _S_KUBUN, KYOSHUTU, _S_KEITAI] * kw)

    for A in (G.Tokubetukokko_Nendomatu, G.Tokubetukokko_Nendomatu_P):
        A[sn, _S_NENREI, _S_SHURUI, KAKYU] *= c_kakyu
        A[sn, _S_NENREI, _S_SHURUI, KIHON] *= c_kihon.reshape(-1, 1)


# ---------------------------------------------------------------------------
# 5. 年度末値 → 年度間値
# ---------------------------------------------------------------------------
def _kaitei(nendo, nenrei, keitai):
    """`Atamawari.c:1109` の改定率の選び方。"""
    ei = nendo - ECON_SHONENDO
    if nenrei <= UNDER_67 or keitai == KAKYU:
        return G.kaiteiritu[ei][UNDER_67 - UNDER_67]
    return G.kaiteiritu[ei][nenrei - UNDER_67]


def _cal_kyufu_nendokan(nendo, nenrei, sho, kyufu, kn, knP):
    """Atamawari.c:1064 の忠実移植。制度・新旧・区分・対象の軸をまとめる。"""
    sn = nendo - SHONENDO
    j = nenrei - NENREI_SUM
    idx = (_S_SEIDO, _S_SHINKYU, _S_KUBUN, _S_TAISHOU)

    for keitai in range(KIHON, KAKYU + 1):
        kaitei = _kaitei(nendo, nenrei, keitai)
        zennen = knP[idx[0], sn - 1, j - 1, idx[1], idx[2], idx[3], keitai]
        if nenrei == UNDER_64:
            tounen = (kn[idx[0], sn, j - 1, idx[1], idx[2], idx[3], keitai]
                      + kn[idx[0], sn, j, idx[1], idx[2], idx[3], keitai])
        else:
            tounen = kn[idx[0], sn, j, idx[1], idx[2], idx[3], keitai]

        kyufu[idx[0], sn, j, idx[1], idx[2], idx[3], keitai] = (
            zennen * (sho + 6 * kaitei) / 12.
            + tounen * (6 - sho) / 12.)


def _cal_kokko_nendokan(nendo, nenrei, sho, kokko, kn, knP):
    """Atamawari.c:1134 の忠実移植。"""
    sn = nendo - SHONENDO
    j = nenrei - NENREI_SUM

    for keitai in range(KIHON, KAKYU + 1):
        kaitei = _kaitei(nendo, nenrei, keitai)
        zennen = knP[_S_SEIDO, sn - 1, j - 1, _S_SHINKYU, _S_KUBUN, keitai]
        if nenrei == UNDER_64:
            tounen = (kn[_S_SEIDO, sn, j - 1, _S_SHINKYU, _S_KUBUN, keitai]
                      + kn[_S_SEIDO, sn, j, _S_SHINKYU, _S_KUBUN, keitai])
        else:
            tounen = kn[_S_SEIDO, sn, j, _S_SHINKYU, _S_KUBUN, keitai]

        kokko[_S_SEIDO, sn, j, _S_SHINKYU, _S_KUBUN, keitai] = (
            zennen * (sho + 6 * kaitei) / 12.
            + tounen * (6 - sho) / 12.)


def _cal_tokubetukokko_nendokan(nendo, nenrei, sho, tk, kn, knP):
    """Atamawari.c:1200 の忠実移植。"""
    sn = nendo - SHONENDO
    j = nenrei - NENREI_SUM

    for keitai in range(KIHON, KAKYU + 1):
        kaitei = _kaitei(nendo, nenrei, keitai)
        zennen = knP[sn - 1, j - 1, _S_SHURUI, keitai]
        if nenrei == UNDER_64:
            tounen = (kn[sn, j - 1, _S_SHURUI, keitai]
                      + kn[sn, j, _S_SHURUI, keitai])
        else:
            tounen = kn[sn, j, _S_SHURUI, keitai]

        tk[sn, j, _S_SHURUI, keitai] = (
            zennen * (sho + 6 * kaitei) / 12.
            + tounen * (6 - sho) / 12.)


# ---------------------------------------------------------------------------
# 7. 単価と拠出金
# ---------------------------------------------------------------------------
_K = slice(SUM, KAKYU + 1)                      # 形態 0〜2
_J64_END = slice(_J64, _JEND)                   # 64〜115歳
_ALLSEIDO = slice(SUM, SHIGAKU + 1)             # 0〜5


def _tanka_kyoshutukin(nendo):
    """Atamawari.c:321-481 の忠実移植。"""
    sn = nendo - SHONENDO
    St = G.SanteiTaishou
    st_sum = St[SUM][sn][SUM]

    # ---- 年度間値の単価と拠出金（64〜115歳） ----
    G.Tanka[sn, _J64_END, _K] = (
        G.Kyufu[SUM, sn, _J64_END, SUM, SUM, KYOSHUTU, _K]
        / st_sum / 12.)
    G.Tanka_Kokko[sn, _J64_END, _K] = (
        G.Kokko[SUM, sn, _J64_END, SUM, SUM, _K] / st_sum / 12)

    G.Kyoshutukin[_ALLSEIDO, sn, _J64_END, _K] = (
        St[_ALLSEIDO, sn, SUM].reshape(-1, 1, 1)
        * G.Tanka[sn, _J64_END, _K] * 12)
    G.Kyoshutukin_Kokko[_ALLSEIDO, sn, _J64_END, _K] = (
        St[_ALLSEIDO, sn, SUM].reshape(-1, 1, 1)
        * G.Tanka_Kokko[sn, _J64_END, _K] * 12)

    # ---- 年齢計（64〜115歳を昇順に足す） ----
    G.Kyoshutukin[_ALLSEIDO, sn, NENREI_SUM - NENREI_SUM, _K] += \
        np.add.accumulate(
            G.Kyoshutukin[_ALLSEIDO, sn, _J64_END, _K], axis=1)[:, -1, :]
    G.Kyoshutukin_Kokko[_ALLSEIDO, sn, NENREI_SUM - NENREI_SUM, _K] += \
        np.add.accumulate(
            G.Kyoshutukin_Kokko[_ALLSEIDO, sn, _J64_END, _K],
            axis=1)[:, -1, :]

    G.Tanka[sn, NENREI_SUM - NENREI_SUM, _K] += \
        np.add.accumulate(G.Tanka[sn, _J64_END, _K], axis=0)[-1]
    G.Tanka_Kokko[sn, NENREI_SUM - NENREI_SUM, _K] += \
        np.add.accumulate(G.Tanka_Kokko[sn, _J64_END, _K], axis=0)[-1]

    # ---- 年度末値の単価と拠出金（63〜115歳） ----
    J = _S_NENREI
    if st_sum > 0.:
        G.Tanka_Nendomatu[sn, J, _K] = (
            G.Kyufu_Nendomatu[SUM, sn, J, SUM, SUM, KYOSHUTU, _K]
            / st_sum / 12.)
        G.Tanka_Kokko_Nendomatu[sn, J, _K] = (
            G.Kokko_Nendomatu[SUM, sn, J, SUM, SUM, _K] / st_sum / 12.)
    else:
        G.Tanka_Nendomatu[sn, J, _K] = 0.
        G.Tanka_Kokko_Nendomatu[sn, J, _K] = 0.

    if nendo == SAISHUNENDO:
        if st_sum > 0.:
            G.Tanka_Nendomatu_P[sn, J, _K] = (
                G.Kyufu_Nendomatu_P[SUM, sn, J, SUM, SUM, KYOSHUTU, _K]
                / st_sum / 12.)
            # 癖 2. ここだけ `_P` でない方を読む
            G.Tanka_Kokko_Nendomatu_P[sn, J, _K] = (
                G.Kokko_Nendomatu[SUM, sn, J, SUM, SUM, _K] / st_sum / 12.)
        else:
            G.Tanka_Nendomatu_P[sn, J, _K] = 0.
            G.Tanka_Kokko_Nendomatu_P[sn, J, _K] = 0.
    else:
        st_next = St[SUM][sn + 1][SUM]
        if st_next > 0.:
            G.Tanka_Nendomatu_P[sn, J, _K] = (
                G.Kyufu_Nendomatu_P[SUM, sn, J, SUM, SUM, KYOSHUTU, _K]
                / st_next / 12.)
            G.Tanka_Kokko_Nendomatu_P[sn, J, _K] = (
                G.Kokko_Nendomatu_P[SUM, sn, J, SUM, SUM, _K]
                / st_next / 12.)
        else:
            G.Tanka_Nendomatu_P[sn, J, _K] = 0.
            G.Tanka_Kokko_Nendomatu_P[sn, J, _K] = 0.

    # ---- 制度別の拠出金（癖 3. 制度計は作らない） ----
    stv = St[_S_SEIDO, sn, SUM].reshape(-1, 1, 1)
    G.Kyoshutukin_Nendomatu[_S_SEIDO, sn, J, _K] = (
        stv * G.Tanka_Nendomatu[sn, J, _K] * 12.)
    G.Kyoshutukin_Kokko_Nendomatu[_S_SEIDO, sn, J, _K] = (
        stv * G.Tanka_Kokko_Nendomatu[sn, J, _K] * 12.)

    if nendo == SAISHUNENDO:
        stvp = St[_S_SEIDO, sn, SUM].reshape(-1, 1, 1)
    else:
        stvp = St[_S_SEIDO, sn + 1, SUM].reshape(-1, 1, 1)
    G.Kyoshutukin_Nendomatu_P[_S_SEIDO, sn, J, _K] = (
        stvp * G.Tanka_Nendomatu_P[sn, J, _K] * 12.)
    G.Kyoshutukin_Kokko_Nendomatu_P[_S_SEIDO, sn, J, _K] = (
        stvp * G.Tanka_Kokko_Nendomatu_P[sn, J, _K] * 12.)

    # ---- 年齢計（63〜115歳を昇順に足す） ----
    for A in (G.Kyoshutukin_Nendomatu, G.Kyoshutukin_Nendomatu_P,
              G.Kyoshutukin_Kokko_Nendomatu,
              G.Kyoshutukin_Kokko_Nendomatu_P):
        A[_S_SEIDO, sn, NENREI_SUM - NENREI_SUM, _K] += \
            np.add.accumulate(A[_S_SEIDO, sn, J, _K], axis=1)[:, -1, :]
