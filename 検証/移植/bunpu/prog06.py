# -*- coding: utf-8 -*-
"""
プログラム/分布推計/prog06.cpp の忠実移植
=========================================
条件に当たる個人に、残り枠のある状態コードを1つ割り当てる。
`func06a` は 2059〜2063年度、`func06b` は 2064〜2069年度に呼ばれる
（`main.cpp:177-182`）。

やっていること（読み解いた範囲）
--------------------------------
1. 個人ごとに、次の全部に当たるかを見る
   - `var007` が 80 でも 90 でも 99 でもない
   - `var035 == 9`
   - `var037 != 1`（まだこの処理を受けていない）
   - `var038 <= 閾値`
2. 当たったら状態コードの候補（`k`）を順に見て、**残り枠があれば**
   `var008` にその状態コードを入れ、枠を1つ使って `var037 = 1` を立て、
   `break` する

枠の管理は2つの表でしている。

    arg06a5（main.cpp の vector030）  使った数（増やす）
    arg06a6（main.cpp の vector029）  残りの数（減らす）

上限は `arg06a4`（vector026 = 遷移表）の文字列を `std::stoi` したもの。

閾値（`prog06.cpp:6-24`）

    func06a: object01c == 0 なら 414。そうでなければ基準年齢で
             51以上→414 / 49,50→426 / 47,48→438 / 45,46→450 /
             43,44→462 / それ以外→474
    func06b: 120 - (70 - 年度) * 12

原本の癖をそのまま残しているところ
----------------------------------
1. **`var007 != 90` は一覧に無い値を見ている（が、意味がある）**
   状態コードの一覧（`main.cpp:36`）は
   `{11..20, 31..34, 40, 50, 60, 70, 80, 99}` で **90 は無い**。
   けれど `main.cpp:147` がその年度に追加した人に `var008 = 90` を入れ、
   同じ年度の `main.cpp:160-161` が `var007 = var008` と写すので、
   **`var007 == 90` の人は実在する**。この条件は「その年度に入った
   ばかりの人を外す」働きをしていて、書き間違いではない。
   （`検証/原本の不具合.md` E7）

2. **`k` のループが 0〜9 なのに使うのは一部だけ**
   `func06a` は `if (k==0 || k==1 || k==9)`、`func06b` は
   `if (k==0 || k==9)`。残りの `k` は何もせず回る。

3. **`func09a` が 99 を返すと配列の外に出る**
   `arg06a5[func09a(var007)][k]` の添字に `func09a` の戻り値を使うが、
   `func09a`（prog09.cpp:5）は状態コード20種以外を渡されると **99** を
   返す。`vector030` の行数は遷移表の行数なので、99 行は無い。
   上の判定で 80/90/99 は外しているが、一覧に無い値（例えば 0）が
   `var007` に入ると範囲外になる。実データでは起きない。
   （`検証/原本の不具合.md` を参照）
"""
from cppnum import stoi
from prog09 import func09a

__all__ = ["func06a", "func06b"]


def func06a(arg06a1, arg06a2, arg06a3, arg06a4, arg06a5, arg06a6,
            arg06a7, arg06a8):
    """prog06.cpp:5 の忠実移植。2059〜2063年度に呼ばれる。

    arg06a1  人数
    arg06a2  状態コードの一覧（vector001）
    arg06a3  個人のリスト（書き換える）
    arg06a4  上限の表（vector026、文字列）
    arg06a5  使った数（vector030、書き換える）
    arg06a6  残りの数（vector029、書き換える）
    arg06a7  object01c.value001
    arg06a8  基準年齢（loop_var002）
    """
    var06a1 = 0
    if arg06a7 == 0:
        var06a1 = 414
    else:
        if arg06a8 >= 51:
            var06a1 = 414
        elif arg06a8 == 49 or arg06a8 == 50:
            var06a1 = 426
        elif arg06a8 == 47 or arg06a8 == 48:
            var06a1 = 438
        elif arg06a8 == 45 or arg06a8 == 46:
            var06a1 = 450
        elif arg06a8 == 43 or arg06a8 == 44:
            var06a1 = 462
        else:
            var06a1 = 474

    for i in range(arg06a1):
        o = arg06a3[i]
        # var007 != 90 は常に真（状態コードに 90 が無い）
        if (o.var007 != 80 and o.var007 != 90 and o.var007 != 99
                and o.var035 == 9 and o.var037 != 1
                and o.var038 <= var06a1):
            r = func09a(o.var007)
            for k in range(0, 10):
                if k == 0 or k == 1 or k == 9:
                    if arg06a5[r][k] < stoi(arg06a4[r][k]):
                        o.var008 = arg06a2[k]
                        arg06a5[r][k] += 1
                        arg06a6[r][k] -= 1
                        o.var037 = 1
                        break


def func06b(arg06b1, arg06b2, arg06b3, arg06b4, arg06b5, arg06b6, arg06b7):
    """prog06.cpp:41 の忠実移植。2064〜2069年度に呼ばれる。

    arg06b1  年度（loop_var003）
    arg06b2  人数
    arg06b3  状態コードの一覧
    arg06b4  個人のリスト（書き換える）
    arg06b5  上限の表（文字列）
    arg06b6  使った数（書き換える）
    arg06b7  残りの数（書き換える）

    閾値が年度で動く（`120 - (70 - 年度) * 12`）。2070年度なら 120、
    2064年度なら 120 - 72 = 48。
    """
    for i in range(arg06b2):
        o = arg06b4[i]
        if (o.var007 != 80 and o.var007 != 90 and o.var007 != 99
                and o.var035 == 9 and o.var037 != 1
                and o.var038 <= (120 - (70 - arg06b1) * 12)):
            r = func09a(o.var007)
            for k in range(0, 10):
                if k == 0 or k == 9:
                    if arg06b6[r][k] < stoi(arg06b5[r][k]):
                        o.var008 = arg06b3[k]
                        arg06b6[r][k] += 1
                        arg06b7[r][k] -= 1
                        o.var037 = 1
                        break
