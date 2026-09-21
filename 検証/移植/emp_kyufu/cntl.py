# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/cntl.cpp の忠実移植（標準入力と設定値）
=============================================================
②は標準入力から**10個**（`key` が 12・13 なら13個）読む。
`main.cpp` が先に4つ、`cntl()` が残りを読む。

    main.cpp   key      11 通常試算 / 12 過去分試算 / 13 受給者分試算
               iname    試算番号（4桁）
               iecon    経済要素ファイル番号（4桁）
               iwname   外枠の試算番号（4桁。1000 以上を assert）
    cntl.cpp   psly     基準年度（**key が 12・13 のときだけ**）
               pslsi    障害・遺族の扱い（同）
               pslsi2   加給・振替加算の扱い（同）
               seimei   将来生命表（4 死亡中位 / 5 高位 / 6 低位）
               flg_part 適用拡大（0〜5）
               flg_sigo 基礎年金の45年化（0〜1）
               flg_kozax 高在老（65歳以上）の廃止（0〜1）
               houjou   標報月額の上限引上げ（0〜3）
               flg_inout 生存脱退力の経年変化（0 進展 / 1 漸進 / 2 現状）

`run_pipeline.sh` は `key = 11` を渡すので `psly` `pslsi` `pslsi2` は
読まれず 0 になる。

決め打ちしている値
------------------
    partyr1 = 16   2016年10月の適用拡大（501人以上）
    partyr2 = 22   2022年10月（101人以上）
    partyr3 = 24   2024年10月（51人以上）
    partyr4 = 27   オプションの適用拡大（`flg_part >= 1` のときだけ。
                   そうでなければ `KE + 2` = 127 で「起こらない」）
    canyr   = 31   基礎年金の45年化を始める年度
    kozaxyr = 27   高在老廃止（`flg_kozax == 1` のときだけ）
    houjouyr = 27  標報上限引上げ（`houjou >= 1` のときだけ）
    seiy    = 70   生命表の基準年
    kzn     = 1
    xb = 115 / xa = 64 / hikrate = 0.95 / chinsura = 1 / kaite = 1
    flg_kaisho = 2 / flg_sankyu = 1

上限引上げの倍率（`houjou`）
----------------------------
    1（75万円）  houjour1 = 1.016 , houjour2 = 1.005
    2（83万円）  houjour1 = 1.024 , houjour2 = 1.008
    3（98万円）  houjour1 = 1.036 , houjour2 = 1.011

`set_kflcan()` — 基礎年金の加入可能年数
---------------------------------------
`kflcan[k][C19(kx)]` は「`kx` 年度生まれ（正確には 20 歳になる年度）の
人が `k` 年度に持てる基礎年金の加入可能年数」。既定は 40 年。

`flg_sigo >= 1`（45年化）なら、`canyr`（2031）年度から3年ごとに
1年ずつ 45 年まで伸ばす。**生まれ年による上限**と**年度による上限**の
小さい方を採る。

```c
if     (canyr <= k && k <= canyr + 2)  kmax = 41.0;   /* 年度の上限 */
...
if     (canyr + 0 - 60 <= kx && kx <= canyr + 1 - 60) kflcan = min(41.0, kmax);
```

原本の癖をそのまま残しているところ
----------------------------------
1. **`if(true)` / `else` の枝が9か所ある。**`else` の方（決め打ち）は
   1行も通らない。標準入力から読むかどうかを切り替えるための名残。
   （`検証/原本の不具合.md`）

2. **`set_kflcan` の中に `if(flg_sigo >= 1)` が二重にある**
   （`cntl.cpp:191` と `:197`）。外側で入っているので内側は常に真。

3. **`set_kflcan` の局所変数 `k` がグローバルの `k` を隠す。**
   `static void set_kflcan()` の中で `int k, kx;` を宣言しているので、
   グローバルの `k`（年度のループ変数）は変わらない。隠すのが
   意図なら正しいが、同名なので読みにくい。

4. **`kzny` `kver` `oldflg` などに1回も代入しない。**`cntl()` は
   設定値を100個近く持つが、触るのは半分ほど。残りは 0 のまま
   （C の静的領域なので 0 で始まる）。

5. **`assert` が9か所。**`-DNDEBUG` を付けずに建てるので有効。
   範囲外の入力はここで落ちる。
"""
from glva import G
from setconst import C19, ENDY, KE, STTY

__all__ = ["cntl", "set_kflcan"]


def cntl(scan):
    """cntl.cpp:9 の忠実移植。`scan` は標準入力を1つずつ返すもの。"""
    if G.key == 12 or G.key == 13:
        print("")
        print("基準年度を指定してください")
        print("  25: 2025年度～")
        G.psly = scan.int_()
    else:
        G.psly = 0

    if G.key == 12 or G.key == 13:
        print("基準年度：%d年度" % (G.psly + 2000))

    if G.key == 12 or G.key == 13:
        print("障害、遺族の扱いを指定してください")
        print("  2: すべて将来分として扱う")
        G.pslsi = scan.int_()
        print("加給、振替加算等の扱いを指定してください")
        print("  1: すべて将来分として扱う")
        G.pslsi2 = scan.int_()
    else:
        G.pslsi = 0
        G.pslsi2 = 0

    print("将来生命表の設定をして下さい")
    print("  4: 新人口2023.4(死亡中位）")
    print("  5: 新人口2023.4(死亡高位)")
    print("  6: 新人口2023.4(死亡低位)")
    G.seimei = scan.int_()
    assert 4 <= G.seimei <= 6, "seimei = %d" % G.seimei

    if 4 <= G.seimei <= 6:
        G.seiy = 70

    G.kzn = 1

    print("被用者保険の更なる適用拡大を行いますか？")
    print("  0: 行わない(通常試算、2020年改正反映後)")
    print("  1: 行う（オプション90万人、企業規模要件撤廃＋５人以上非適用業種廃止）")
    print("  2: 行う（オプション200万人、１＋賃金要件撤廃または最賃引上げ）")
    print("  3: 行う（オプション270万人、２＋５人未満個人事業所も適用)")
    print("  4: 行う（オプション860万人、週10時間以上の全ての被用者)")
    print("  5: 行う（現行制度で最低賃金が上昇した場合の効果)")
    G.flg_part = scan.int_()
    assert 0 <= G.flg_part <= 5, "flg_part = %d" % G.flg_part

    G.partyr1 = 16
    G.partyr2 = 22
    G.partyr3 = 24

    if G.flg_part >= 1:
        G.partyr4 = 27
    else:
        G.partyr4 = KE + 2

    print("基礎年金の45年化を行いますか？")
    print("  0: 行わない（通常試算）")
    print("  1: 行う（オプション、45年化）")
    G.flg_sigo = scan.int_()
    assert 0 <= G.flg_sigo <= 1, "flg_sigo = %d" % G.flg_sigo

    G.canyr = 31

    set_kflcan()

    print("高在老（65歳以上）の廃止を行いますか？")
    print("  0: 行わない（通常試算）")
    print("  1: 行う(オプション)")
    G.flg_kozax = scan.int_()
    assert 0 <= G.flg_kozax <= 1, "flg_kozax = %d" % G.flg_kozax

    if G.flg_kozax == 1:
        G.kozaxyr = 27
    else:
        G.kozaxyr = KE + 1

    G.kozax = 65

    print("標報月額の上限の引き上げを行いますか？")
    print("  0: 行わない（通常試算）")
    print("  1: 行う（オプション、上限75万円）")
    print("  2: 行う（オプション、上限83万円）")
    print("  3: 行う（オプション、上限98万円）")
    G.houjou = scan.int_()
    assert 0 <= G.houjou <= 3, "houjou = %d" % G.houjou

    if G.houjou >= 1:
        G.houjouyr = 27
        if G.houjou == 1:
            G.houjour1 = 1.016
            G.houjour2 = 1.005
        elif G.houjou == 2:
            G.houjour1 = 1.024
            G.houjour2 = 1.008
        elif G.houjou == 3:
            G.houjour1 = 1.036
            G.houjour2 = 1.011

    print("生存脱退力の経年変化を行いますか")
    print("  0: 行う（労働参加進展）")
    print("  1: 行う（労働参加漸進）")
    print("  2: 行わない（労働参加現状）")
    G.flg_inout = scan.int_()

    G.flg_hantei = 0
    G.flg_okure = 0
    G.flg_kurisage = 0
    G.flg_tuuroutest = 0
    G.flg_hsr = 0
    G.hsr_endy = 40
    G.hsr_r = 1.3e-2
    G.flg_siktuika = 0
    G.flg_toukei = 0
    G.flg_gtest = 0
    G.flg_bzwtest = 0
    G.chinsura = 1
    G.kaite = 1
    G.nenbeex = 0
    G.xb = 115
    G.xa = 64
    G.cht_flg = 1
    G.hikrate = 0.95
    G.flg_hiho70 = 0
    G.hiho70yr = KE + 1
    G.flg_kaisho = 2
    G.flg_sankyu = 1
    G.nenbe65 = 0


def set_kflcan():
    """cntl.cpp:182 の `static void set_kflcan()`。

    局所変数 `k` がグローバルの `k` を隠す（癖 3.）。移植版は局所変数
    なので同じ（`G.k` は変わらない）。
    """
    canyr = G.canyr

    # 既定は 40 年。kx = -74 〜 ENDY、k = STTY 〜 ENDY
    G.kflcan[STTY:ENDY + 1, C19(-74):C19(ENDY) + 1] = 40.0

    if G.flg_sigo >= 1:
        for kx in range(canyr - 60, ENDY + 1):
            for k in range(canyr, ENDY + 1):
                if k - kx < 0:
                    continue

                kmax = 40.0
                # 癖 2. 外側で入っているので常に真
                if G.flg_sigo >= 1:
                    if canyr <= k <= canyr + 2:
                        kmax = 41.0
                    elif k <= canyr + 5:
                        kmax = 42.0
                    elif k <= canyr + 8:
                        kmax = 43.0
                    elif k <= canyr + 11:
                        kmax = 44.0
                    elif canyr + 12 <= k:
                        kmax = 45.0

                    if canyr + 0 - 60 <= kx <= canyr + 1 - 60:
                        G.kflcan[k][C19(kx)] = min(41.0, kmax)
                    elif canyr + 2 - 60 <= kx <= canyr + 3 - 60:
                        G.kflcan[k][C19(kx)] = min(42.0, kmax)
                    elif canyr + 4 - 60 <= kx <= canyr + 5 - 60:
                        G.kflcan[k][C19(kx)] = min(43.0, kmax)
                    elif canyr + 6 - 60 <= kx <= canyr + 7 - 60:
                        G.kflcan[k][C19(kx)] = min(44.0, kmax)
                    elif canyr + 8 - 60 <= kx:
                        G.kflcan[k][C19(kx)] = min(45.0, kmax)
