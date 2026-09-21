# -*- coding: utf-8 -*-
"""
プログラム/厚生年金/収支計算/shus_out.c の忠実移植
===================================================
⑤の出力。`01shushi.*`（制度別の収支見通し）と `03summary.*`（所得代替率の
サマリ）、カット率ファイル、特別調整率ファイルを書く。
`検証/オプション試算/compare_option.py` が読むのはこの2本。

書式は C の printf をそのまま写す。Python の書式指定は C と同じ変換を
使うので（`%20.13e` ↔ `f"{x:20.13e}"`）一致する。`検証/移植/test_cnum.py`
が実測で押さえている。

原本の癖をそのまま残しているところ
----------------------------------
1. **出力関数がグローバルを書き換える**
   `shus_shushiout` は `Cc[21]`（現在価格の積立金）、`Cc[26]`（積立度合）、
   `Cc[27]`（保険料率）、`Cc[28]`（賦課保険料率）を**出力のついでに計算**
   している。`shus_nin_out` は `Ap[0]` と `Ap65[0]` に足し込み、`Ukyu[0]` を
   作る。`shus_summary` は `Cc[0]`・`Dc[0]`・`Jisout[0]` を書き換える。
   つまり「出力」と言いながら状態が変わるので、呼ぶ順序に意味がある。

2. **`Siwake` と `Dc` は値が入らない**
   `shus_out.c:252` は `Siwake[ii]` を出すが、`Siwake` はどこにも代入が無い
   （BSS のゼロのまま）。`Dc` も `shus_summary` の中で 0 を入れて 0 を
   足すだけ。どちらも常に 0 が出る。

3. **`shus_summary` の最後で `Cc[0]` を壊す**（shus_out.c:476-489）
   拠出金の基準年度（`Kyoskijun`=15）までの `Cc[0]` をゼロにしてから
   制度別を足し直す。だから「収支[全厚年２:収支用]」の表は
   「収支[全厚年１:tou]」と前半の年度が違う。

4. **調整最終年度は後ろから探す**（shus_out.c:157）
   `Escutrrh[k-1][67]` が前年より **1.0E-13 より大きく**なった最初の年度。
   調整率は年々下がるので、下がり止まった所が終了年度。
   見つからない、または `Ke-1` に等しいときは「-」を出す。
"""
from cnum import nround
from cntl import ii2psd
from glva import G
from setconst import (ECEDY, ECSTY, ECXA, ENDY, FLKE, FLKS, MAX, NY, STTY,
                      XA, XB)


def shus_econ_out():
    """shus_out.c:10 経済前提の一覧を 01shushi の先頭に書く。"""
    is_, ie = 0, 4

    for ii in range(is_, ie + 1):
        ofp = G.ofp01_shushi[ii]

        ofp.fp("経済前提等\n")
        ofp.fp("年度,物価,賃金,運用利回り,比例改定率,比例既裁68歳,"
               "基礎改定率,基礎既裁68歳,\n")
        for k in range(5, G.Ke + 1):
            ofp.fp(f"{k:3d}, {float(G.Ci[k - ECSTY]) * 100.0:5.2f}, "
                   f"{float(G.H[k - ECSTY]) * 100.0:5.2f}, "
                   f"{float(G.Ri[k - ECSTY]) * 100.0:5.2f}, ")
            ofp.fp(f"{(float(G.Krb[k - ECSTY, 67 - ECXA]) - 1.0) * 100.0:5.2f}, "
                   f"{(float(G.Krb[k - ECSTY, 68 - ECXA]) - 1.0) * 100.0:5.2f}, "
                   f"{(float(G.Kra[k - ECSTY, 67 - ECXA]) - 1.0) * 100.0:5.2f}, "
                   f"{(float(G.Kra[k - ECSTY, 68 - ECXA]) - 1.0) * 100.0:5.2f},\n")
        ofp.fp("\n")


def shus_nin_out():
    """shus_out.c:35 被保険者数と受給者数の一覧を書く。

    ついでに `Ap[0]` / `Ap65[0]`（4制度合計）と `Ukyu[0]` を作る。
    """
    # double t4sx[5][4][7][ENDY-STTY+1]
    t4sx = [[[[0.0] * NY for _ in range(7)] for _ in range(4)]
            for _ in range(5)]

    is_, ie = 1, 4

    for ii in range(is_, ie + 1):
        s2 = 3 if ii <= 1 else 2

        for s in range(0, s2 + 1):
            for i in range(0, 7):
                for k in range(G.Ks + 1, G.Ke + 1):
                    a = t4sx[ii][s][i]
                    b = t4sx[0][s][i]
                    for x in range(XA - 1, XB + 1):
                        v = float(G.T4xtp[ii, s, i, k - STTY, x])
                        a[k - STTY] += v
                        b[k - STTY] += v

        for s in range(0, s2 + 1):
            for k in range(G.Ks + 1, G.Ke + 1):
                G.Ap[0, s, k - STTY] += G.Ap[ii, s, k - STTY]
                G.Ap65[0, s, k - STTY] += G.Ap65[ii, s, k - STTY]

    is_ = 0

    for ii in range(is_, ie + 1):
        ofp = G.ofp01_shushi[ii]

        s2 = 3 if ii <= 1 else 2

        ofp.fp("年度,被保険者,老齢,老在,通老,通在,障害,遺族,")
        ofp.fp("被保険者・男,被保険者・女,")
        ofp.fp("65歳以上被保険者・男,65歳以上被保険者・女,")
        ofp.fp("老齢①,老在①,通老①,通在①,障害①,遺族①,")
        ofp.fp("老齢②,老在②,通老②,通在②,障害②,遺族②,")
        if s2 == 3:
            ofp.fp("老齢③,老在③,通老③,通在③,障害③,遺族③")
        ofp.fp("\n")

        for k in range(FLKS, FLKE + 1):
            ofp.fp(f"{k:3d},")
            ofp.fp(f"{float(G.Ap[ii, 0, k - STTY]):14.8e},")
            for i in range(1, 7):
                ofp.fp(f"{t4sx[ii][0][i][k - STTY]:14.8e},")
            ofp.fp(f"{float(G.Ap[ii, 1, k - STTY]) + float(G.Ap[ii, 3, k - STTY]):14.8e},"
                   f"{float(G.Ap[ii, 2, k - STTY]):14.8e},")
            ofp.fp(f"{float(G.Ap65[ii, 1, k - STTY]) + float(G.Ap65[ii, 3, k - STTY]):14.8e},"
                   f"{float(G.Ap65[ii, 2, k - STTY]):14.8e},")
            for s in range(1, s2 + 1):
                for i in range(1, 7):
                    ofp.fp(f"{t4sx[ii][s][i][k - STTY]:14.8e},")
            ofp.fp("\n")

    if G.Saimu == 0 or G.Saimu == 1 or G.Saimu == 2:
        for ii in range(1, 5):
            for i in range(1, 7):
                if i == 1 or i == 2:
                    s = 0
                elif i <= 4:
                    s = 1
                else:
                    s = i - 3
                for k in range(FLKS, FLKE + 1):
                    v = t4sx[ii][0][i][k - STTY]
                    G.Ukyu[0, ii, s, k - STTY] += v
                    G.Ukyu[0, 0, s, k - STTY] += v


def _kend(arr, Ks, Ke):
    """調整最終年度を後ろから探す（shus_out.c:154）。

    `arr[k-1][67]` が前年より 1.0E-13 より大きくなった最初の年度。
    見つからなければ 0。
    """
    kend = 0
    dtemp = float(arr[Ke - 1 - ECSTY, 67 - ECXA])
    for k in range(Ke - 1, Ks, -1):
        if float(arr[k - 1 - ECSTY, 67 - ECXA]) - dtemp > 1.0E-13:
            kend = k
            break
        else:
            dtemp = float(arr[k - 1 - ECSTY, 67 - ECXA])
    return kend


def shus_shushiout(mode):
    """shus_out.c:133 収支見通しの表を書く。

    mode=0 はスライド調整前、mode=1 は調整後。
    `Cc[21][26][27][28]` を出力のついでに計算する。
    """
    # 単位。i<=25 と i==30 は 億円（1e-8）、27/28 は率（×100）、他はそのまま
    tanni = [0.0] * 31
    for i in range(0, 31):
        if i <= 25 or i == 30:
            tanni[i] = 1.0E-8
        elif i == 27 or i == 28:
            tanni[i] = 1.0E+2
        else:
            tanni[i] = 1.0

    is_, ie = 0, 4

    kend_h = kend_t = 0
    if mode == 1:
        kend_h = _kend(G.Escutrrh, G.Ks, G.Ke)
        kend_t = _kend(G.Escutrrt, G.Ks, G.Ke)

    for ii in range(is_, ie + 1):
        ofp = G.ofp01_shushi[ii]

        if mode == 1:
            if ii == 1:
                print(" 調整最終年度 ", end="")
            ofp.fp("\n調整最終年度, ")

            if kend_h != 0 and kend_h != G.Ke - 1:
                v = float(G.Escutrrh[MAX(0, kend_h - ECSTY), 67 - ECXA])
                if ii == 1:
                    print(f" 厚年：{kend_h:3d} ({v * 100.:.13f}) ", end="")
                ofp.fp(f" 厚年, {kend_h:3d}, {v:20.14e}, ")
            else:
                v = float(G.Escutrrh[G.Ke - 1 - ECSTY, 67 - ECXA])
                if ii == 1:
                    print(f" 厚年： -  ({v:20.14e})", end="")
                ofp.fp(" 厚年, - , - , ")

            if kend_t != 0 and kend_t != G.Ke - 1:
                v = float(G.Escutrrt[MAX(0, kend_t - ECSTY), 67 - ECXA])
                if ii == 1:
                    print(f" 国年：{kend_t:3d} ({v * 100.:.13f})")
                ofp.fp(f" 国年, {kend_t:3d}, {v:20.14e}\n")
            else:
                v = float(G.Escutrrt[G.Ke - 1 - ECSTY, 67 - ECXA])
                if ii == 1:
                    print(f" 国年： -  ({v:20.14e})")
                ofp.fp(" 国年, - , - \n")

        ofp.fp("\n")

        if mode == 0:
            ofp.fp("\n収支見通し【スライド調整前】\n")
        else:
            ofp.fp("\n収支見通し【スライド調整後】\n")

        ofp.fp("年度,収入計,保険料収入,(再)上乗せ分,運用収入,国庫負担,")
        ofp.fp("(再)国庫基礎,(再)国庫経過比例,(再)国庫経過定額,")
        ofp.fp("(再)国庫かさ上げ,支援額収入,納付金,")
        ofp.fp("支出計,独自給付,(再)独自比例,(再)独自定額系,")
        ofp.fp("(再)独自加給,基礎年金拠出金,事務費,支援額支出,")
        ofp.fp("収支差,年度末積立金,積立金(現在価格),")
        ofp.fp("(再)パート保険料,総報酬総額,総報酬額,育児報酬額,積立度合,"
               "保険料率,賦課保険料率,,")
        ofp.fp("妻積み分配等,\n")

        for k in range(FLKS, FLKE + 1):
            if k >= ECSTY and k <= ECEDY:
                G.Cc[ii, 21, k - STTY] = (G.Cc[ii, 20, k - STTY]
                                          / G.Id_Hhd[k - ECSTY])
            else:
                G.Cc[ii, 21, k - STTY] = 0.

            if G.Cc[ii, 11, k - STTY] > 0.:
                G.Cc[ii, 26, k - STTY] = (G.Cc[ii, 20, k - 1 - STTY]
                                          / G.Cc[ii, 11, k - STTY])
            else:
                G.Cc[ii, 26, k - STTY] = 0.

            psd = 1 if ii == 0 else ii2psd(ii)

            if k >= ECSTY and k <= ECEDY:
                G.Cc[ii, 27, k - STTY] = G.Prema[psd, k - STTY]

            if G.Cc[ii, 23, k - STTY] > 0.:
                G.Cc[ii, 28, k - STTY] = (
                    (G.Cc[ii, 11, k - STTY] - G.Cc[ii, 2, k - STTY]
                     - G.Cc[ii, 4, k - STTY] - G.Cc[ii, 9, k - STTY]
                     - G.Cc[ii, 10, k - STTY]) / G.Cc[ii, 24, k - STTY])
            else:
                G.Cc[ii, 28, k - STTY] = 0.

            ofp.fp(f"{k:3d},")
            for i in range(0, 31):
                if ii == 1 or k != G.Kyoskijun - 1 or i != 30:
                    v = float(G.Cc[ii, i, k - STTY]) * tanni[i]
                else:
                    # Siwake はどこにも代入が無いので常に 0（BSS のまま）
                    v = float(G.Siwake[ii]) * tanni[i]
                ofp.fp(f"{v:20.13e},")
            ofp.fp("\n")


def shus_cutout():
    """shus_out.c:262 次回の計算に渡すカット率ファイルを書く。

    2005〜2008年度は 1.0 固定、2009年度以降は解いた調整率。
    """
    ofp = G.ofp_cuta
    for k in range(5, 9):
        ofp.fp(f"{k:4d},")
        for i in range(63, 116):
            ofp.fp(f"{1.:20.14e},")
        ofp.fp("\n")
    for k in range(9, FLKE + 1):
        ofp.fp(f"{k:4d},")
        for i in range(63, 116):
            ofp.fp(f"{float(G.Escutrrt[k - ECSTY, i - ECXA]):20.14e},")
        ofp.fp("\n")

    ofp = G.ofp_cutb
    for k in range(5, 9):
        ofp.fp(f"{k:4d},")
        for i in range(63, 116):
            ofp.fp(f"{1.:20.14e},")
        ofp.fp("\n")
    for k in range(9, FLKE + 1):
        ofp.fp(f"{k:4d},")
        for i in range(63, 116):
            ofp.fp(f"{float(G.Escutrrh[k - ECSTY, i - ECXA]):20.14e},")
        ofp.fp("\n")

    if G.Touitu >= 1:
        ofp = G.ofp_cuta2
        for k in range(5, 9):
            ofp.fp(f"{k:4d},")
            for i in range(63, 116):
                ofp.fp(f"{1.:20.14e},")
            ofp.fp("\n")
        for k in range(9, FLKE + 1):
            ofp.fp(f"{k:4d},")
            for i in range(63, 116):
                ofp.fp(f"{float(G.Escutrrt[k - ECSTY, i - ECXA]):20.14e},")
            ofp.fp("\n")

        ofp = G.ofp_cutb2
        for k in range(5, 9):
            ofp.fp(f"{k:4d},")
            for i in range(63, 116):
                ofp.fp(f"{1.:20.14e},")
            ofp.fp("\n")
        for k in range(9, FLKE + 1):
            ofp.fp(f"{k:4d},")
            for i in range(63, 116):
                ofp.fp(f"{float(G.Escutrrh[k - ECSTY, i - ECXA]):20.14e},")
            ofp.fp("\n")


def shus_summary():
    """shus_out.c:326 所得代替率のサマリ（03summary）を書く。

    `検証/オプション試算/compare_option.py` が所得代替率を読むのはこの表。
    最後に `Cc[0]` を作り直す（拠出金の基準年度までをゼロにしてから
    制度別を足し直す）ので、その前後で「全厚年」の意味が変わる。
    """
    ofp = G.ofp03_summary

    if G.Saimu == 0:
        ofp.fp(f"{G.Nfile}, {G.Nfile2}, {G.Nfile3}\n")
    else:
        ofp.fp(f"{G.Saimushu}, {G.Nfile}, {G.Nfile2}, {G.Nfile3}\n")
    ofp.fp(f"{G.Ecfile}, {G.Wcfile}\n")
    if G.Saimu == 0:
        ofp.fp(f"{G.Nkfile}\n")
    else:
        ofp.fp(f"{G.Saimuski}, {G.Nkfile}\n")

    ofp.fp(f"{G.Sifile}, 予備:, {G.Cutrfile4}, Cntlset:, {G.Cntlset}, "
           f"Seidn:, {G.Seidn}\n")

    ofp.fp("\n")
    ofp.fp(f"Flg_Part,{G.Flg_Part},, Flg_Dmakuro,{G.Flg_Dmakuro}\n\n")

    kend_h = _kend(G.Escutrrh, G.Ks, G.Ke)
    kend_t = _kend(G.Escutrrt, G.Ks, G.Ke)

    ofp.fp(f"終了年度：,厚年,{kend_h:d},"
           f"{1.0 - float(G.Escutrrh[G.Ke - ECSTY, 67 - ECXA]):20.14e},"
           f"国年,{kend_t:d}, "
           f"{1.0 - float(G.Escutrrt[G.Ke - ECSTY, 67 - ECXA]):20.14e}\n\n")

    ofp.fp("経済前提等\n")
    ofp.fp("年度,物価,賃金,運用利回り,比例改定率,比例既裁68歳,"
           "基礎改定率,基礎既裁68歳,")
    ofp.fp("モデル年金額,うち比例,うち基礎,可処分所得,")
    ofp.fp("所得代替率,うち比例,うち基礎,（参考）所得代替率(一元化前),")
    ofp.fp("比例カット67,比例カット68,基礎カット67,基礎カット68,mファイル,")
    ofp.fp("モデル年金額（物価割り戻し）,うち比例（物価割り戻し）,"
           "うち基礎（物価割り戻し）,可処分所得（物価割り戻し）\n")

    k_model = 24

    r1 = r1h = r1k = r2 = r2h = r2k = 0.
    for k in range(5, G.Ke + 1):
        ofp.fp(f"{k:3d}, {float(G.Ci[k - ECSTY]) * 100.0:5.2f}, "
               f"{float(G.H[k - ECSTY]) * 100.0:5.2f}, "
               f"{float(G.Ri[k - ECSTY]) * 100.0:5.2f}, ")
        ofp.fp(f"{(float(G.Krb[k - ECSTY, 67 - ECXA]) - 1.0) * 100.0:20.14e}, "
               f"{(float(G.Krb[k - ECSTY, 68 - ECXA]) - 1.0) * 100.0:20.14e}, "
               f"{(float(G.Kra[k - ECSTY, 67 - ECXA]) - 1.0) * 100.0:20.14e}, "
               f"{(float(G.Kra[k - ECSTY, 68 - ECXA]) - 1.0) * 100.0:20.14e}, ")
        if k >= k_model:
            r1h = (float(G.Mhirei[k - STTY, 0])
                   * float(G.Escutrrh[k - ECSTY, 67 - ECXA]))
            r1k = (float(G.Mkiso[k - STTY])
                   * float(G.Escutrrt[k - ECSTY, 67 - ECXA]))
            r2h = (float(G.Mhirei[k - STTY, 1])
                   * float(G.Escutrrh[k - ECSTY, 67 - ECXA]))
            r2k = (float(G.Mkiso[k - STTY])
                   * float(G.Escutrrt[k - ECSTY, 67 - ECXA]))
        if k == k_model:
            # 基準年度だけ円単位に丸める（nround は 0 から遠い方へ）
            r1h = nround(r1h, 0)
            r2h = nround(r2h, 0)
            r1k = nround(r1k, 0)
            r2k = nround(r2k, 0)
        r1 = r1h + r1k
        r2 = r2h + r2k
        if k >= k_model:
            kw0 = float(G.Kw[k - STTY, 0])
            kw1 = float(G.Kw[k - STTY, 1])
            ofp.fp(f"{r1:20.14e}, {r1h:20.14e}, {r1k:20.14e}, {kw0:20.14e}, ")
            ofp.fp(f"{r1 / kw0 * 100.:20.14e}, {r1h / kw0 * 100.:20.14e}, "
                   f"{r1k / kw0 * 100.:20.14e}, {r2 / kw1 * 100.:20.14e}, ")
        else:
            ofp.fp(f"{0.:20.14e}, {0.:20.14e}, {0.:20.14e}, {0.:20.14e}, ")
            ofp.fp(f"{0.:20.14e}, {0.:20.14e}, {0.:20.14e}, {0.:20.14e}, ")
        ofp.fp(f"{float(G.Escutrrh[k - ECSTY, 67 - ECXA]):20.14e}, "
               f"{float(G.Escutrrh[k - ECSTY, 68 - ECXA]):20.14e}, "
               f"{float(G.Escutrrt[k - ECSTY, 67 - ECXA]):20.14e}, "
               f"{float(G.Escutrrt[k - ECSTY, 68 - ECXA]):20.14e}, "
               f"{float(G.Scutrk1[k - ECSTY]):20.14e},")
        if k >= k_model:
            idc = float(G.Id_Cid[k - ECSTY])
            ofp.fp(f"{r1 / idc:20.14e}, {r1h / idc:20.14e}, "
                   f"{r1k / idc:20.14e}, "
                   f"{float(G.Kw[k - STTY, 0]) / idc:20.14e},\n")
        else:
            ofp.fp(f"{0.:20.14e}, {0.:20.14e}, {0.:20.14e}, {0.:20.14e},\n")
    ofp.fp("\n")

    ofp.fp("\n,全厚年,,,,,旧厚年,,,,,国共,,,,,地共,,,,,私学,,,,,\n")
    ofp.fp("年度,")
    for ii in range(0, 5):
        ofp.fp("被保険者,老齢相当,通老相当,障害,遺族,")
    ofp.fp("\n")
    for k in range(FLKS, FLKE + 1):
        ofp.fp(f"{k:3d},")
        G.Ap[0, 0, k - STTY] = G.Ap[1, 0, k - STTY]
        for ii in range(2, 5):
            G.Ap[0, 0, k - STTY] += G.Ap[ii, 0, k - STTY]
        for ii in range(0, 5):
            ofp.fp(f"{float(G.Ap[ii, 0, k - STTY]):20.14e}, "
                   f"{float(G.Ukyu[0, ii, 0, k - STTY]):20.14e}, "
                   f"{float(G.Ukyu[0, ii, 1, k - STTY]):20.14e}, "
                   f"{float(G.Ukyu[0, ii, 2, k - STTY]):20.14e}, "
                   f"{float(G.Ukyu[0, ii, 3, k - STTY]):20.14e},")
        ofp.fp("\n")
    ofp.fp("\n")

    ofp.fp("収支[全厚年１:tou]\n\n")
    _shushi_header(ofp)
    for k in range(FLKS, FLKE + 1):
        ofp.fp(f"{k:3d},")
        for i in range(0, 31):
            if (i == 2 or i == 7 or i == 8 or (13 <= i <= 15) or i == 22
                    or (i >= 25 and i != 27 and i != 30)):
                continue
            if i == 6:
                dtemp = (float(G.Cc[0, 6, k - STTY]) + float(G.Cc[0, 7, k - STTY])
                         + float(G.Cc[0, 8, k - STTY]))
            else:
                dtemp = float(G.Cc[0, i, k - STTY])
            if i != 27:
                dtemp /= 1.0E+8
            else:
                dtemp *= 100.
            ofp.fp(f"{dtemp:20.14e},")
        ofp.fp(f"{float(G.Jyutaku[k - STTY]) / 1.0E+8:20.14e},,")
        for i in range(0, 4):
            ofp.fp(f"{0.:20.14e},")
        ofp.fp("\n")
    ofp.fp("\n\n")

    # 【重要】ここで Cc[0] を作り直す（shus_out.c:476）
    for k in range(FLKS, G.Kyoskijun + 1):
        for i in range(0, 31):
            if k != G.Kyoskijun or (i != 20 and i != 21):
                G.Cc[0, i, k - STTY] = 0.
            if k == G.Kyoskijun:
                G.Dc[0, i] = 0.
            if (i != 0 and i != 3 and i != 19 and i != 20 and i != 21
                    and (i <= 25 or i == 30)):
                for ii in range(1, 5):
                    G.Cc[0, i, k - STTY] += G.Cc[ii, i, k - STTY]
                    if k == G.Kyoskijun:
                        G.Dc[0, i] += G.Dc[ii, i]
    G.Jisout[0] = 0.
    for ii in range(2, 5):
        G.Jisout[0] += G.Jisout[ii]

    for ii in range(0, 5):
        ofp.fp("\n")
        if ii == 0:
            ofp.fp("収支[全厚年２:収支用]\n\n")
        if ii == 1:
            ofp.fp("収支[旧厚年]\n\n")
        if ii == 2:
            ofp.fp("収支[国共済]\n\n")
        if ii == 3:
            ofp.fp("収支[地共済]\n\n")
        if ii == 4:
            ofp.fp("収支[私学共済]\n\n")
        _shushi_header(ofp)
        for k in range(FLKS, FLKE + 1):
            ofp.fp(f"{k:3d},")
            for i in range(0, 31):
                if (i == 2 or i == 7 or i == 8 or (13 <= i <= 15) or i == 22
                        or (i >= 25 and i != 27 and i != 30)):
                    continue
                if i == 6:
                    dtemp = (float(G.Cc[ii, 6, k - STTY])
                             + float(G.Cc[ii, 7, k - STTY])
                             + float(G.Cc[ii, 8, k - STTY]))
                else:
                    dtemp = float(G.Cc[ii, i, k - STTY])
                if i != 27:
                    dtemp /= 1.0E+8
                else:
                    dtemp *= 100.
                ofp.fp(f"{dtemp:20.14e},")
            if ii <= 1:
                ofp.fp(f"{float(G.Jyutaku[k - STTY]) / 1.0E+8:20.14e},,")
            else:
                ofp.fp(f"{0.:20.14e},,")
            for i in range(0, 4):
                ofp.fp(f"{float(G.Ukyu[1, ii, i, k - STTY]):20.14e},")
            ofp.fp("\n")
        ofp.fp("\n\n")


def _shushi_header(ofp):
    """shus_out.c:449 と 501 の見出し（同じ内容が2箇所にある）。"""
    ofp.fp("年度,")
    ofp.fp("収入計, 保険料, 運用収入, 国庫負担, うち基礎, うち経過的国庫, "
           "支援入, 納付金,")
    ofp.fp("支出計,独自給付,基礎年金拠出金,福祉,支援出,収支差,")
    ofp.fp("積立金, 現在価値, 総報酬, 総報酬(育児等除く), 保険料率,妻積み,"
           "住宅融資（別掲）,,")
    ofp.fp("老齢相当,通老相当,障害,遺族\n")


def shus_Tokutyoout():
    """shus_out.c:534 特別調整率（キャリーオーバーの持ち越し分）を書く。"""
    ofp = G.ofp_Tokutyo

    for k in range(5, G.Ke + 1):
        ofp.fp(f"{k:d},")
        for x in range(67, XB + 1):
            ofp.fp(f"{float(G.Tokutyo[k - ECSTY, x - ECXA]):.15f},")
        ofp.fp("\n")
