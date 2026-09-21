# -*- coding: utf-8 -*-
"""
プログラム/分布推計/prog12.cpp の忠実移植
=========================================
最後の年度（`main.cpp:220`、`loop_var003 == 64`）だけ呼ばれる集計。
3つの表を作り、`prog13` がそれを CSV に書く。

    func12a → vector019（4区分）   どの制度で一番長かったか
    func12b → vector020（7項目）   被用者期間の長さ別の人数と合計月数
    func12c → vector021（8項目）   年金額の階級別の人数と平均月額

集計の対象は **`is_func03()` が偽の人だけ**（`_prototype.h:212`）。
`is_func03()` は

    var008 == 99 か var035 が 1,2 か var009 < 240

なので、その否だと「99でない、var035 が 1 でも 2 でもない、
加入月数が 240（20年）以上」。**受給権のある人**という読み。

func12a — 4区分
---------------
3つの期間を比べて一番長い制度を選ぶ（`prog12.cpp:6-18`）。

    var022  被用者としての期間      → 区分 0
    var010  第1号（国年）の期間     → 区分 1
    var021  第3号の期間             → 区分 2
    どれも240未満                   → 区分 3

同じ長さのときの優先順位が **区分ごとに違う**。区分0は `>=`、
区分1は `var010 > var022` と `var010 >= var021`、区分2は両方 `>`。
つまり「被用者 → 第1号 → 第3号」の順に優先される。

func12b — 期間の長さ別
----------------------
`var022` を 0 / 12 / 120 / 240 / 360 / 480 で区切って人数を数え、
`[6]` に `var022` の合計を積む（`prog12.cpp:26-47`）。
`prog13` が `[6] / 総数 / 12` で平均年数にする。

func12c — 年金額の階級別
------------------------
`var044` を 60万 / 84万 / 120万 / 180万 / 240万 / 300万 で区切る。
`[7]` には月額の平均を入れる（`prog13` が 1万で割る）。

原本の癖をそのまま残しているところ
----------------------------------
1. **`arg12c3[7]` の代入がループの中にある**（`prog12.cpp:88`）
   `if (var12c2!=0) arg12c3[7] = …;` が `for i` の内側・`if` の外側に
   あるので、毎回上書きされる。最後の値だけが残るので**結果は同じ**
   だが、人数ぶん無駄に計算している。

2. **平均は整数除算**（`prog12.cpp:89`）
   `var12c1` と `var12c2` は `long long` なので、
   `(double)(var12c1/var12c2)` で小数が落ちる。
   1人あたりの月額を円単位に丸めていることになる。
   `func10c` と同じ形（`検証/原本の不具合.md`）。

3. **`(long long)(var044/12.0)` も0方向への切り捨て**
   足し込む前に1人ずつ円未満を落としている。

4. **`arg12c3` は double なのに人数を数えている**（`prog12.cpp:78` など）
   `++arg12c3[6]` のように double を1ずつ増やす。人数の範囲では
   double でも正確なので結果は変わらない。

5. **`arg12b3[6] += var022` が6つの枝に同じように書かれている**
   どの枝でも同じことをするので、条件の外に出せる。原本のまま
   6回書いてある。
"""

__all__ = ["func12a", "func12b", "func12c"]


def func12a(arg12a1, arg12a2, arg12a3):
    """prog12.cpp:4 の忠実移植。一番長かった制度で4区分に分ける。

    arg12a1  人数
    arg12a2  個人のリスト（読むだけ）
    arg12a3  書き込み先（vector019、長さ4）
    """
    for j in range(len(arg12a3)):
        arg12a3[j] = 0
    for i in range(arg12a1):
        o = arg12a2[i]
        if o.is_func03():
            continue
        a = o.var022        # 被用者
        b = o.var010        # 第1号
        c = o.var021        # 第3号
        if ((a >= 240 and b < 240 and c < 240)
                or (a >= 240 and b >= 240 and c < 240 and a >= b)
                or (a >= 240 and b < 240 and c >= 240 and a >= c)):
            arg12a3[0] += 1
        elif ((b >= 240 and a < 240 and c < 240)
                or (b >= 240 and a >= 240 and c < 240 and b > a)
                or (b >= 240 and a < 240 and c >= 240 and b >= c)):
            arg12a3[1] += 1
        elif ((c >= 240 and a < 240 and b < 240)
                or (c >= 240 and a >= 240 and b < 240 and c > a)
                or (c >= 240 and a < 240 and b >= 240 and c > b)):
            arg12a3[2] += 1
        elif a < 240 and b < 240 and c < 240:
            arg12a3[3] += 1


# prog12.cpp:26-47。(下限, 入れる添字) を上から順に見る
_BINS12B = ((480, 5), (360, 4), (240, 3), (120, 2), (12, 1), (0, 0))


def func12b(arg12b1, arg12b2, arg12b3):
    """prog12.cpp:24 の忠実移植。被用者期間の長さ別の人数と合計月数。

    arg12b1  人数
    arg12b2  個人のリスト（読むだけ）
    arg12b3  書き込み先（vector020、長さ7）
    """
    for j in range(len(arg12b3)):
        arg12b3[j] = 0
    for i in range(arg12b1):
        o = arg12b2[i]
        if o.is_func03():
            continue
        v = o.var022
        for lo, idx in _BINS12B:
            if v >= lo:
                arg12b3[idx] += 1
                arg12b3[6] += v          # どの枝でも同じ（癖 5.）
                break


# prog12.cpp:56-87。最後だけ `> 0.0`（他は `>=`）なのに注意
_BINS12C = ((3000000.0, 6), (2400000.0, 5), (1800000.0, 4), (1200000.0, 3),
            (840000.0, 2), (600000.0, 1))


def func12c(arg12c1, arg12c2, arg12c3):
    """prog12.cpp:53 の忠実移植。年金額の階級別の人数と平均月額。

    arg12c1  人数
    arg12c2  個人のリスト（読むだけ）
    arg12c3  書き込み先（vector021、長さ8。double）
    """
    for j in range(len(arg12c3)):
        arg12c3[j] = 0.0
    var12c1 = 0        # long long。月額の合計（円未満切り捨て）
    var12c2 = 0        # long long。人数
    for i in range(arg12c1):
        o = arg12c2[i]
        if not o.is_func03():
            v = o.var044
            idx = None
            for lo, k in _BINS12C:
                if v >= lo:
                    idx = k
                    break
            if idx is None and v > 0.0:
                idx = 0                  # 最後の枝だけ `> 0.0`
            if idx is not None:
                arg12c3[idx] += 1        # double を1ずつ（癖 4.）
                # (long long)(x/12.0) は0方向への切り捨て（癖 3.）
                var12c1 += int(v / 12.0)
                var12c2 += 1
        # **この代入はループの中にある**（癖 1.）。整数除算（癖 2.）
        if var12c2 != 0:
            q = abs(var12c1) // abs(var12c2)
            if (var12c1 < 0) != (var12c2 < 0):
                q = -q
            arg12c3[7] = float(q)
