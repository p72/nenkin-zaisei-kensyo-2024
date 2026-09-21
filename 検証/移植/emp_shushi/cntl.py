# -*- coding: utf-8 -*-
"""
プログラム/厚生年金/収支計算/cntl.c の忠実移植
===============================================
標準入力から試算の設定を読む。読む順序は `検証/実行/run_pipeline.sh` の
`emp_stdin()` が組み立てている順序とぴったり対応している。

    0        → Saimu          試算の種類（0:通常試算）
    8        → Fpset          給付水準の決定方法（8:国年先決め均衡計算）
    KAKUDAI  → Flg_Part       適用拡大
    SIGO     → Flg_Sigo       wakuk-m の読み込み先変更（45年化）
    [WAKU_M] → Wcfile2        ↑が1のときだけ
    HOUJOU   → Flg_Houjou     標準報酬上限の見直し
    TOUGOU   → Touitu         厚年勘定に国年勘定を足してカット率を作る
    [YOBI2]  → Cutrfile5      ↑が1以上のときだけ
    1-CARRY  → Flg_Kmakuro    キャリーオーバーの廃止（極性が反転している）
    DMACRO   → Flg_Dmakuro    名目下限の撤廃
    ---- ここから set_filenum()（main.c:73）----
    SHISAN   → Nfile
    ECON     → Ecfile
    WAKU     → Wcfile
    YOBI     → Cutrfile4

原本の癖をそのまま残しているところ
----------------------------------
`if(1){ ... } else { ... }` が随所にある。else 側は「対話せず既定値に
固定する」開発用の枝で、実際には通らない。移植では通る側だけを実装し、
通らない枝の内容はコメントに残した。

`Cbm_Pt1 = 12. * 5./6.` は式の形のまま書く。`10.0` と書いても double では
同値だが、原本の見た目を残しておく方が後の照合で迷わない。
"""
from glva import G


def cntl(scan):
    """cntl.c:12 void cntl(void) の忠実移植。

    `scan` は標準入力を C の scanf のように読むオブジェクト（cscan.Scan）。
    原本は scanf を直に呼ぶので引数が無いが、移植ではテストしやすいように
    入力元を渡す形にした。
    """
    # cntl.c:14 if(1) の通る側。else 側は Saimu = 0 固定。
    print("\n試算の種類を指定してください。")
    print("０:通常試算")
    print("１:過去分試算")
    print("２:受給者分試算")
    G.Saimu = scan.d()

    if G.Saimu < 0 or G.Saimu > 2:
        print(f" 試算の種類の設定が不適切です Saimu={G.Saimu}")
        raise SystemExit(1)

    if G.Saimu != 0:
        print("基準年度を入力して下さい（２桁）")
        print("  25:2025年度～")
        G.Psly = scan.d()

        print("障害、遺族の扱いを指定してください")
        print("  2:すべて将来分として扱う")
        G.Pslsi = scan.d()

        print("加給、振替加算等の扱いを指定してください")
        print("  1:すべて将来分として扱う")
        G.Pslsi2 = scan.d()

        G.Seitaikey = 0

        print("死亡率改善を指定してください")
        print("  1:将来生命表の死亡率改善分だけ改善する方法（平行移動方式）")
        G.Kzn = scan.d()

        if G.Kzn != 1:
            print(f" 想定していない設定値ですKzn={G.Kzn}")
            raise SystemExit(1)
    else:
        G.Psly = G.Pslsi = G.Pslsi2 = G.Seitaikey = 0
        G.Kzn = G.Kzny = 0

    if G.Saimu != 1 and G.Saimu != 2:
        print("\n給付水準の決定方法を選択してください")
        print("  8 : 国年先決め均衡計算（有限均衡）  ＜通常計算＞ ")
        print("  9 : カット率ファイル指定 ")
        G.Fpset = scan.d()
    else:
        G.Fpset = 9

    if G.Fpset == 8 or G.Fpset == 9:
        pass
    else:
        print(" 現在対応していない試算モードです。")
        raise SystemExit(1)

    # cntl.c:73 if(1) の通る側。else 側は Flg_Part = 0 固定。
    print("\n被用者保険の更なる適用拡大を行いますか？")
    print("０：行わない（通常試算、2020年改正反映後）")
    print("１：行う（オプション90万人ベース、企業規模要件撤廃＋非適用業種撤廃）")
    print("２：行う（オプション200万人ベース、１．＋賃金要件撤廃または最賃引上げ）")
    print("３：行う（オプション270万人ベース、２．＋５人未満個人も適用）")
    print("４：行う（オプション860万人ベース、週10時間以上の全ての被用者）")
    print("５：行う（現行制度で最低賃金が上昇した場合の効果）")
    G.Flg_Part = scan.d()
    if G.Flg_Part < 0 or G.Flg_Part > 5:
        print(f"パートフラグ設定エラー Flg_Part={G.Flg_Part}")
        raise SystemExit(1)

    G.Part_Yr1 = 22
    G.Part_Yr2 = 24
    if G.Flg_Part >= 1:
        G.Part_Yr3 = 27
    else:
        G.Part_Yr3 = 0

    G.Cbm_Pt1 = 12. * 5. / 6.

    # cntl.c:100 if(1) の通る側。else 側は Flg_Sigo = 0 固定。
    print("使用するwakuk-mファイルの読み込み先を変更しますか？")
    print("０:しない（通常試算）")
    print("１:する（オプション、45年化）")
    G.Flg_Sigo = scan.d()

    if G.Flg_Sigo == 1:
        print("使用するwaku-mファイルの外枠番号を入力してください（４桁） ")
        G.Wcfile2 = scan.s()          # char Wcfile2[5]

    # cntl.c:114 if(1) の通る側。else 側は Flg_Houjou = 0 固定。
    print("\n標準報酬上限の見直しを行いますか？")
    print("０：行わない（通常試算）")
    print("１：行う（オプション、上限75万円）")
    print("２：行う（オプション、上限83万円）")
    print("３：行う（オプション、上限98万円）")
    G.Flg_Houjou = scan.d()
    if G.Flg_Houjou < 0 or 3 < G.Flg_Houjou:
        print(" 設定値が間違っています Flg_Houjou")
        raise SystemExit(1)

    if G.Flg_Houjou >= 1:
        G.Houjou_Yr = 27
        if G.Flg_Houjou == 1:
            G.Houjou_R1 = 1.016
            G.Houjou_R2 = 1.005
        elif G.Flg_Houjou == 2:
            G.Houjou_R1 = 1.024
            G.Houjou_R2 = 1.008
        elif G.Flg_Houjou == 3:
            G.Houjou_R1 = 1.036
            G.Houjou_R2 = 1.011
    else:
        G.Houjou_Yr = 0
        G.Houjou_R1 = 1.0
        G.Houjou_R2 = 1.0

    # cntl.c:148 if(1) の通る側。else 側は Touitu = 0 固定。
    print("\n厚年勘定に国年勘定を足しこんでカット率を作成しますか？")
    print("０：行わない（通常試算）")
    print("１：行う（オプション準備)")
    G.Touitu = scan.d()
    if G.Touitu < 0 or G.Touitu > 1:
        print(" 設定値が間違っています Touitu")
        raise SystemExit(1)

    if G.Touitu >= 1:
        print("\n国年・厚年別収支見通し作成用の予備番号を入力して下さい（３桁）")
        G.Cutrfile5 = scan.s()        # char Cutrfile5[4]

    # cntl.c:167 if(1) の通る側。else 側は Flg_Kmakuro = 0 固定。
    print("\nキャリーオーバーの廃止を行いますか？")
    print("０:行わない（通常試算）")
    print("１:行う（参考試算）")
    G.Flg_Kmakuro = scan.d()
    if G.Flg_Kmakuro < 0 or G.Flg_Kmakuro > 1:
        print(" キャリーオーバーの設定が間違っていますFlg_Kmakuro="
              f"{G.Flg_Kmakuro}")
        raise SystemExit(1)

    G.Kmakuro_Yr = 18

    if G.Flg_Kmakuro == 1:
        G.Kmakuro_Yr2 = 25
    else:
        G.Kmakuro_Yr2 = 0

    # cntl.c:187 if(1) の通る側。else 側は Flg_Dmakuro = 0, Dmakuro_Yr = 0 固定。
    print("\n名目下限の撤廃を行いますか？")
    print("０：行わない（通常試算）")
    print("１：行う（参考試算）")
    G.Flg_Dmakuro = scan.d()
    if G.Flg_Dmakuro < 0 or G.Flg_Dmakuro > 1:
        print("  名目下限撤廃の設定が間違っていますFlg_Dmakuro="
              f"{G.Flg_Dmakuro}")
        raise SystemExit(1)
    elif G.Flg_Dmakuro == 1:
        G.Dmakuro_Yr = 25
    else:
        G.Dmakuro_Yr = 0

    # cntl.c:207 以降は固定値
    G.zan_jimu = 0

    G.zan_fund = 0
    G.Kijun = 22

    G.kakusa = 2

    G.Flg_shunor = 0
    if G.Flg_shunor == 0:
        G.Shunor = 0.997

    G.Flg_nendo = 1
    if G.Flg_nendo == 1:
        G.nendohosei = 1.000

    G.Flg_matsu = 0
    G.Ca = 1.0

    G.Nenbeex = 0
    G.Nenbeex2 = 1
    G.Kkuci = 0
    G.zaichou = 0
    G.Sienset = 1
    G.Flg_Jimu = 2
    G.Cntlset = 1
    G.Seidn = 0
    G.Pseid = 0
    G.Flg_Kaisho = 2
    G.Misyu = 0.
    G.Tumawake = 0.
    G.Kyoskijun = 15


def ii2usd(ii):
    """cntl.c:241 の忠実移植。制度の通し番号 ii を U-sys の番号に直す。"""
    if ii < 0 or 4 < ii:
        print(f"ii2usd関数の引数が間違っています ii={ii}")
        raise SystemExit(1)

    if G.Seidn != 0:
        usd = G.Useid
    else:
        if ii == 1:
            usd = 0
        elif ii == 2:
            usd = 1
        elif ii == 3:
            usd = 4
        elif ii == 4:
            usd = 5
        else:
            print(f"ii2usd関数の引数が間違っています Seidn={G.Seidn}, ii={ii}")
            raise SystemExit(1)
    return usd


def ii2psd(ii):
    """cntl.c:269 の忠実移植。制度の通し番号 ii を P-sys の番号に直す。"""
    if ii < 0 or 4 < ii:
        print(f"ii2psd関数の引数が間違っています ii={ii}")
        raise SystemExit(1)

    if G.Seidn != 0:
        if G.Seidn <= 4:
            psd = G.Seidn
        else:
            psd = 1
    else:
        if ii < 1 or 4 < ii:
            print(f"ii2psd関数の引数が間違っています Seidn={G.Seidn}, ii={ii}")
            raise SystemExit(1)
        psd = ii

    return psd
