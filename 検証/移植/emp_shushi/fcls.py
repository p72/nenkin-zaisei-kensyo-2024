# -*- coding: utf-8 -*-
"""
プログラム/厚生年金/収支計算/fcls.c の忠実移植
===============================================
開いたファイルを閉じる。

原本の不具合を1つ踏んでいる（パッチ後の挙動に合わせてある）
-----------------------------------------------------------
`fcls.c:64` は `fclose(ifp_Touitu)` を**無条件に**呼ぶ。しかし
`fopn.c:69` は `Touitu >= 1` のときだけ開くので、通常試算（Touitu==0）では
NULL のまま渡る。glibc の fclose(NULL) は segfault する。

これは既に `検証/実行/patches/glibc-portability.patch` の1つ目のハンクが
`if(ifp_Touitu != NULL) fclose(ifp_Touitu);` に直している。C 版も
そのパッチを当てて走っているので、移植でも同じ守りを入れる（パッチは
計算結果を変えない。仕様書 §12.2）。

なお `ofp03_summary`・`ifp_sien`・`ofp_siwake`・`ofp_NPBPkekka`・
`ofp_EPsummary`・`ofp_test` は **閉じられていない**。C では正常終了時に
標準ライブラリが flush するので出力は落ちない。Python でも同じになるよう、
close_all() の最後で開いたまま残っているものを flush する。
"""
from cfile import fclose
from glva import G


def alfclose():
    """fcls.c:10 void alfclose(void) の忠実移植。"""
    fclose(G.ifp_econ)

    for i in range(1, 5):
        fclose(G.ifp10_usys[i])

    fclose(G.ifp_kyos)

    fclose(G.ifp27_tuma)

    fclose(G.ifp_nofu)

    fclose(G.ifp_kaiteb)

    if G.Cutrfile1[:1] == "0":
        fclose(G.ifp_kaitea)
    elif G.Cutrfile1[:1] == "1":
        fclose(G.ifp_kokukaite)

    if G.Fpset != 9:
        fclose(G.ifp_wakum)

    if G.Cutrfile1[:1] == "1" and G.Fpset == 8:
        fclose(G.ifp_bas_cuta)
    elif G.Fpset == 9:
        fclose(G.ifp_asys_cuta)
        fclose(G.ifp_asys_cutb)

    if G.Fpset != 9:
        fclose(G.ofp_cuta)
        fclose(G.ofp_cutb)

        if G.Touitu >= 1:
            fclose(G.ofp_cuta2)
            fclose(G.ofp_cutb2)

    is_ = 0

    if G.Saimu == 0 or G.Saimu == 1 or G.Saimu == 2:
        for i in range(is_, 5):
            fclose(G.ofp01_shushi[i])
            if G.Nenbeex2 == 1:
                fclose(G.ofp90_nenbe[i])

    fclose(G.ofp_Tokutyo)

    # fcls.c:64 原本は無条件。パッチ後の挙動（NULL を避ける）に合わせる。
    fclose(G.ifp_Touitu)

    # 原本が閉じ忘れているもの。C は正常終了時に flush するので、
    # ここで同じことをする（閉じる順序は出力内容に影響しない）。
    fclose(G.ofp03_summary)
    fclose(G.ifp_sien)
    fclose(G.ofp_siwake)
    fclose(G.ofp_NPBPkekka)
    fclose(G.ofp_EPsummary)
    fclose(G.ofp_test)
