# -*- coding: utf-8 -*-
"""
被保険者推計/fout.c の忠実移植
==============================
①の本体の出力。61ファイル書く。

    waku{BANGO}-{00..57}.csv   分類 × 性 × 年度 × 年齢       58本
    waku{BANGO}-nenreikei.csv  年度末の年齢計（分類を横に並べる）
    waku{BANGO}-nenkeikan.csv  年度間（前年度末と当年度末の平均）
    waku{BANGO}-settei.csv     設定値の控え

58 の「分類」（`bunrui`）
------------------------
`fout.c:37-440` の `switch`。中身は既にできている配列から選ぶだけ。

     0  公的年金の被保険者計（45年化のときは XEND 以上を別式）
     1  被用者計（厚年＋共済＋パート。70歳以上は厚年を除く）
     2  国年2号（15〜64歳の被用者）
     3  旧厚（70歳未満）
     4  旧厚（70歳以上）
     5  旧厚12種（パート含まず）
     6  旧厚3種
     7  パート（適用拡大の対象者）
     8  国共済2号   9 地共済2号  10 私学2号
    11  1号計      12 1号（一般） 13 1号（任意）
    14  3号計      15 旧厚3号     16 国共3号  17 地共3号  18 私学3号
    19  未加入外（70歳未満）
    20  人口（年央）    21 人口（年度末）
    22〜25  適用拡大（現行 = ykubun 1）の計・元1号・元3号・元その他
    26〜41  適用拡大1段階目の増分（ykubun 2 − ykubun 1）
    42〜57  適用拡大2段階目の増分（ykubun 3 − ykubun 2）

26〜41 は `PART >= 1 && nendo >= PARTYR1` のときだけ、
42〜57 は `PART == 2 && nendo >= PARTYR2` のときだけ値が入る。

年齢の足し方（**順序が結果に出る**）
-----------------------------------
`fout.c:441-444` は年齢 15〜120 を**昇順に1つずつ**足す。

```c
nenrei_kei_ninzu[bunrui][y][sei] += nenrei_betu_ninzu[nenrei] ;
if ( nenrei > 100 ) nenrei_betu_ninzu[100] += nenrei_betu_ninzu[nenrei] ;
```

浮動小数の足し算は順序で結果が変わるので、移植版も**同じ順**で足す。
NumPy の `np.sum` は対和（pairwise）で順序が違うため使えない。
代わりに `np.add.accumulate`（＝逐次の累積和）の最後の要素を取る。
これが C の逐次加算と1ビットも違わないことは実測で確かめた
（`検証/移植/test_hihoken_num.py`）。

原本の癖をそのまま残しているところ
----------------------------------
1. **`-nenkeikan.csv` の最初の年度が未初期化の値を読む**（`fout.c:525`）

   ```c
   double nenrei_kei_ninzu[69][ENDY-STARTY+1][5] ;   /* 初期化なしの自動変数 */
   ...
   for ( nendo = KS ; nendo <= KF ; nendo++ )        /* KS = 2021 */
     nenrei_kei_ninzu[bunrui][nendo-STARTY][sei] = 0.0 ;   /* 添字 1..105 */
   ...
   raund( ( nenrei_kei_ninzu[bunrui][nendo-STARTY][sei]
          + nenrei_kei_ninzu[bunrui][nendo-1-STARTY][sei] ) / 2.0 , 0 )
   ```

   `nendo == KS` のとき2つ目の添字が **0** になるが、そこは一度も
   代入されていない（`KS-STARTY == 1` から埋めている）。つまり
   **未初期化の自動変数を読んで出力に出している**（未定義動作）。

   実測では 0 が入っていて、2021年度の値が「年度末の半分」になる。
   `waku3001-nenkeikan.csv` の2021年度 公的計 = 33,691,054 は
   `waku3001-nenreikei.csv` の 67,382,109 のおよそ半分で、これに当たる。
   **年度間の平均になっていない。** 移植版は 0 で作るので同じ値が出る。
   （`検証/原本の不具合.md`）

2. **`nenrei_betu_ninzu[100]` を足したあとに `nenrei_kei_ninzu` を足す**
   順序は「switch で値を入れる → 計に足す → 100 に寄せる」。
   `nenrei == 100` の周回では switch の値が計に入り、そのあと
   101〜120 が 100 に寄せられる。`計` と `100の列` は別々に積むので
   二重計上にはならない。

3. **分類 2 が 65歳以上を 0 にする**（`fout.c:59`）
   `nenrei < 65` の条件。国年2号が65歳までという制度に対応する。

4. **`%lf` は `%f` と同じ**。`printf` の `%lf` は `double` を
   6桁の小数で出す。移植版も `f"{x:f}"`。

5. **`nenrei_kei_ninzu` の第1添字が 69 だが使うのは 0〜57**
   （`fout.c:14`）。58 以上は触らない。
"""
import math
import sys

import numpy as np

from fopn import P
from glva import G
from cnum import raund
from setconst import ENDY, KF, KIJUN, KS, STARTY

__all__ = ["fout"]

NB = 58                 # 分類の数（0〜57）
A0, A1 = 15, 121        # 年齢 15〜120（106個）
KEI_OFF = 100 - A0      # nenrei == 100 のときの添字（85）


def fmt6(x):
    """C の `printf("%lf", x)`。＝ `%f`（小数6桁）。"""
    if math.isnan(x):
        return "-nan" if math.copysign(1.0, x) < 0 else "nan"
    if math.isinf(x):
        return "-inf" if x < 0 else "inf"
    return f"{x:f}"


def _vec(bunrui, y, sei):
    """`fout.c:37-440` の `switch` を、年齢 15〜120 のベクトルで返す。

    原本は年齢ごとにスカラーで求めるが、どの分類も年齢について
    **要素ごとの演算**なのでベクトルにしても1ビットも変わらない。
    """
    ichigou, sangou, nigou = G.ichigou, G.sangou, G.nigou
    kounen, partnin = G.kounen, G.partnin
    mika, jc, jm = G.mika_soto, G.jinko_c, G.jinko_m
    z = np.zeros(A1 - A0, dtype=np.float64)

    def pn(p, t, yk):
        return partnin[y, sei, A0:A1, p, t, yk]

    if bunrui == 0:
        v = (ichigou[0, y, sei, A0:A1] + nigou[y, sei, A0:A1]
             + sangou[0, y, sei, A0:A1] + pn(0, 0, 0)).copy()
        if G.MODE45 == 1:
            XEND = int(G.xend[y])
            if XEND < A1:
                k = max(XEND, A0) - A0
                v[k:] = (ichigou[2, y, sei, XEND:A1]
                         + nigou[y, sei, XEND:A1]
                         + partnin[y, sei, XEND:A1, 0, 0, 0])
        return v
    if bunrui == 1:
        v = (kounen[0, y, sei, A0:A1] + pn(0, 0, 0)).copy()
        v[70 - A0:] -= kounen[1, y, sei, 70:A1]
        return v
    if bunrui == 2:
        v = z.copy()
        v[:65 - A0] = (kounen[0, y, sei, A0:65]
                       + partnin[y, sei, A0:65, 0, 0, 0])
        return v
    if bunrui == 3:
        v = z.copy()
        v[:70 - A0] = (kounen[1, y, sei, A0:70]
                       + partnin[y, sei, A0:70, 0, 0, 0])
        return v
    if bunrui == 4:
        v = z.copy()
        v[70 - A0:] = kounen[1, y, sei, 70:A1]
        return v
    if bunrui == 5:
        return kounen[2, y, sei, A0:A1]
    if bunrui == 6:
        return kounen[3, y, sei, A0:A1]
    if bunrui == 7:
        return pn(0, 0, 0)
    if bunrui in (8, 9, 10):
        return kounen[bunrui - 4, y, sei, A0:A1]
    if bunrui in (11, 12, 13):
        return ichigou[bunrui - 11, y, sei, A0:A1]
    if bunrui == 14:
        return sangou[0, y, sei, A0:A1]
    if bunrui == 15:
        return sangou[1, y, sei, A0:A1]
    if bunrui in (16, 17, 18):
        return sangou[bunrui - 12, y, sei, A0:A1]
    if bunrui == 19:
        v = z.copy()
        v[:70 - A0] = mika[y, sei, A0:70]
        return v
    if bunrui == 20:
        return jc[y, sei, A0:A1]
    if bunrui == 21:
        return jm[y, sei, A0:A1]
    # 22〜25：現行（ykubun 1）そのまま
    if bunrui in (22, 23, 24, 25):
        p = (0, 1, 2, 7)[bunrui - 22]
        return pn(p, 0, 1)
    # 26〜41：1段階目の増分、42〜57：2段階目の増分
    ent = _DIFF.get(bunrui)
    if ent is not None:
        p, t, stage = ent
        nendo = y + STARTY
        if stage == 1:
            if G.PART >= 1 and nendo >= G.PARTYR1:
                return pn(p, t, 2) - pn(p, t, 1)
        else:
            if G.PART == 2 and nendo >= G.PARTYR2:
                return pn(p, t, 3) - pn(p, t, 2)
        return z
    raise AssertionError(f"分類 {bunrui} は fout.c に無い")


# fout.c:152-439。26〜57 の (pkubun, tkubun, 段階) 対応表
_DIFF = {
    26: (0, 0, 1), 27: (1, 0, 1), 28: (2, 0, 1), 29: (7, 0, 1),
    30: (0, 2, 1), 31: (0, 1, 1), 32: (0, 3, 1),
    33: (1, 2, 1), 34: (1, 1, 1), 35: (1, 3, 1),
    36: (2, 2, 1), 37: (2, 1, 1), 38: (2, 3, 1),
    39: (7, 2, 1), 40: (7, 1, 1), 41: (7, 3, 1),
    42: (0, 0, 2), 43: (1, 0, 2), 44: (2, 0, 2), 45: (7, 0, 2),
    46: (0, 2, 2), 47: (0, 1, 2), 48: (0, 3, 2),
    49: (1, 2, 2), 50: (1, 1, 2), 51: (1, 3, 2),
    52: (2, 2, 2), 53: (2, 1, 2), 54: (2, 3, 2),
    55: (7, 2, 2), 56: (7, 1, 2), 57: (7, 3, 2),
}

# fout.c:465-471 / 502-508 の性別の見出し
_SEI_LABEL = ("男女計", "男", "女", "女有配偶", "女無配偶")

# fout.c:472-484 の列見出し（-nenreikei / -nenkeikan で共通）
_HEAD = (
    "公的計,被用者計,国年２号,旧厚(70未満),旧厚(70以上),"
    "旧厚12種(パート含まず),旧厚3種,"
    "旧厚短時間(今後の適用拡大対象者を含む),国共2号,地共2号,私学2号,"
    "1号計,1号(一般),1号(任意),3号計,旧厚3号,国共3号,地共3号,私学3号,"
    "人口差分,人口央,人口末,"
    "適用拡大202410計,適用拡大202410元１号,適用拡大202410元３号,"
    "適用拡大202410元その他,"
    "適用拡大１段階目計,適用拡大１段階目元１号,適用拡大１段階目元３号,"
    "適用拡大１段階目元その他,"
    "適用拡大１段階目元週30時間以上,適用拡大１段階目元週20～30時間,"
    "適用拡大１段階目元週20時間未満,"
    "適用拡大１段階目元１号週30時間以上,適用拡大１段階目元１号週20～30時間,"
    "適用拡大１段階目元１号週20時間未満,"
    "適用拡大１段階目元３号週30時間以上,適用拡大１段階目元３号週20～30時間,"
    "適用拡大１段階目元３号週20時間未満,"
    "適用拡大１段階目元その他週30時間以上,"
    "適用拡大１段階目元その他週20～30時間,"
    "適用拡大１段階目元その他週20時間未満,"
    "適用拡大２段階目計,適用拡大２段階目元１号,適用拡大２段階目元３号,"
    "適用拡大２段階目元その他,"
    "適用拡大２段階目元週30時間以上,適用拡大２段階目元週20～30時間,"
    "適用拡大２段階目元週20時間未満,"
    "適用拡大２段階目元１号週30時間以上,適用拡大２段階目元１号週20～30時間,"
    "適用拡大２段階目元１号週20時間未満,"
    "適用拡大２段階目元３号週30時間以上,適用拡大２段階目元３号週20～30時間,"
    "適用拡大２段階目元３号週20時間未満,"
    "適用拡大２段階目元その他週30時間以上,"
    "適用拡大２段階目元その他週20～30時間,"
    "適用拡大２段階目元その他週20時間未満\n"
)


def _open_w(path):
    try:
        return open(path, "w", encoding="utf-8", newline="")
    except OSError:
        print("出力wakuファイルを開けません!", file=sys.stderr)
        raise SystemExit(2)


def fout():
    """fout.c:8 の忠実移植。"""
    BANGO = G.BANGO
    # double nenrei_kei_ninzu[69][131][5]。**初期化なしの自動変数**（癖 1.）。
    # 実測で 0 が入っていたので 0 で作る
    kei = np.zeros((69, ENDY - STARTY + 1, 5), dtype=np.float64)

    # ---- 分類別の58本。fout.c:19-455 ----
    for bunrui in range(NB):
        out = [f"試算番号, BANGO=, {BANGO}\n", "分類,性,年度,計,"]
        out.append("".join(f"{ii:02d}," for ii in range(15, 100)))
        out.append("100\n")
        for sei in range(0, 5):
            for nendo in range(KS, KF + 1):
                y = nendo - STARTY
                v = np.asarray(_vec(bunrui, y, sei), dtype=np.float64)
                # 年齢を昇順に足す（順序が結果に出る）
                kei[bunrui, y, sei] = np.add.accumulate(v)[-1]
                v100 = np.add.accumulate(v[KEI_OFF:])[-1]
                out.append(f"{bunrui:4d},{sei:1d},{nendo:4d},")
                out.append(fmt6(raund(float(kei[bunrui, y, sei]), 0)) + ",")
                out.append("".join(
                    fmt6(raund(float(v[i]), 0)) + ","
                    for i in range(0, 100 - A0)))
                out.append(fmt6(raund(float(v100), 0)) + "\n")
        with _open_w(P.waku(BANGO, bunrui)) as f:
            f.write("".join(out))

    # ---- 年度末の年齢計。fout.c:458-493 ----
    out = [f"年度末,試算番号,BANGO=,{BANGO}\n"]
    for sei in range(0, 5):
        out.append(_SEI_LABEL[sei] + ",")
        out.append(_HEAD)
        for nendo in range(KS, KF + 1):
            y = nendo - STARTY
            out.append(f"{nendo:4d},")
            out.append("".join(
                fmt6(raund(float(kei[b, y, sei]), 0)) + ","
                for b in range(0, 57)))
            out.append(fmt6(raund(float(kei[57, y, sei]), 0)) + ",\n")
    with _open_w(P.nenreikei(BANGO)) as f:
        f.write("".join(out))

    # ---- 年度間。fout.c:495-530 ----
    # **nendo == KS のとき y-1 == 0 は未初期化**（癖 1.）
    out = [f"年度間, 試算番号, BANGO=, {BANGO}\n"]
    for sei in range(0, 5):
        out.append(_SEI_LABEL[sei] + ", ")
        out.append(_HEAD)
        for nendo in range(KS, KF + 1):
            y = nendo - STARTY
            out.append(f"{nendo:4d},")
            out.append("".join(
                fmt6(raund((float(kei[b, y, sei])
                            + float(kei[b, y - 1, sei])) / 2.0, 0)) + ","
                for b in range(0, 57)))
            out.append(fmt6(raund((float(kei[57, y, sei])
                                   + float(kei[57, y - 1, sei])) / 2.0,
                                  0)) + ",\n")
    with _open_w(P.nenkeikan(BANGO)) as f:
        f.write("".join(out))

    # ---- 設定値の控え。fout.c:533-557 ----
    s = [
        f"試算番号,BANGO=,{BANGO}\n",
        f"開始年度,STARTY=,{STARTY}\n",
        f"終了年度,ENDY=,{ENDY}\n",
        f"計算モード,MODE=,{G.MODE}\n",
        f"基準年度,KIJUN=,{KIJUN}\n",
        f"出力開始年度,KS=,{KS}\n",
        f"出力終了年度,KF=,{KF}\n",
        f"出生率の設定,JIN=,{G.JIN}\n",
        f"死亡率の設定,QX=,{G.QX}\n",
        f"入国超過の設定,NC=,{G.NC}\n",
        f"人口推計開始年度,SJINKOY=,{G.SJINKOY}\n",
        f"有配偶率年度,YUHAIGY=,{G.YUHAIGY}\n",
        f"労働力率,ROUDR=,{G.ROUDR}\n",
        f"労働力率年度,ROUDYR=,{G.ROUDYR}\n",
        f"パート適用導入の有無,PART=,{G.PART}\n",
        f"パート適用導入年度1,PARTYR1=,{G.PARTYR1}\n",
        f"パート適用導入年度2,PARTYR2=,{G.PARTYR2}\n",
        f"パート基礎数値の年度,PARTKYR=,{G.PARTKYR}\n",
        f"45年化,MODE45=,{G.MODE45}\n",
    ]
    with _open_w(P.settei(BANGO)) as f:
        f.write("".join(s))
