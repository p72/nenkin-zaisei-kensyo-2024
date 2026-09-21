# -*- coding: utf-8 -*-
"""
プログラム/厚生年金/収支計算/main.c の忠実移植
===============================================
⑤の入口。原本の呼び出し順をそのまま守る。

    init_gval()   配列を 1.0 で初期化（glva.py）
    cntl()        標準入力から試算の設定を読む
    set_filenum() 標準入力から試算番号・経済前提番号・外枠番号・予備番号
    alfopen()     入出力ファイルを全部開く
    flck()        入力のヘッダを出力に写し、読む位置をデータ先頭に合わせる
    econ()        経済前提を読む
    rdfl()        ①〜④の結果を読む            ← 未移植
    shus()        収支計算（所得代替率）        ← 未移植
    alfclose()    閉じる

未移植のものを呼ぶと NotImplementedError になる。全部つながるまでは
`検証/移植/test_*.py` の差分テストで部品ごとに突き合わせる。
"""
import sys

import glva
from cscan import Scan
from glva import G


def main(argv=None, scan=None):
    """main.c:23 int main(int ac, char **av) の忠実移植。"""
    if scan is None:
        scan = Scan.from_stdin()

    print("\n<< 初期化等の処理 >>\n")
    glva.init_gval()

    print("<< Cntl開始 >>")
    import cntl as cntl_mod
    cntl_mod.cntl(scan)
    set_filenum(scan)

    print("\n<< FileOpen開始 >>\n")
    import fopn
    fopn.alfopen()

    print("<< FileCheck開始 >>\n")
    import flck
    flck.flck()

    print("<< Econ開始 >>\n")
    import econ as econ_mod
    econ_mod.econ()

    print("<< Rdfl開始 >>\n")
    import rdfl
    rdfl.rdfl()

    print("<< Shus開始 >>\n")
    import shus
    shus.shus()

    print("\n<< FileClose開始 >>\n")
    import fcls
    fcls.alfclose()

    return 0


def set_filenum(scan):
    """main.c:73 void set_filenum(void) の忠実移植。

    Nfile2 / Nfile3 / Nkfile は Nfile の複製。Cutrfile1〜3 は固定値。
    均衡終了年度は Cutrfile3 + 2100 = 2120 年度。
    """
    print("\n試算番号を入力して下さい")
    G.Nfile = scan.s()                    # char Nfile[5]

    G.Nfile2 = G.Nfile
    G.Nfile3 = G.Nfile
    G.Nkfile = G.Nfile

    print("\n経済前提番号を入力して下さい（４桁）")
    G.Ecfile = scan.s()                   # char Ecfile[5]

    print("\n外枠番号を入力して下さい（４桁）")
    G.Wcfile = scan.s()                   # char Wcfile[5]
    itemp = _atoi(G.Wcfile)
    if itemp < 1000 or 9999 < itemp:
        print("  外枠番号の設定が不適切です。")
        raise SystemExit(1)

    G.Cutrfile1 = "1"
    G.Cutrfile2 = "1"
    G.Cutrfile3 = "20"

    print(f"  均衡終了年度を［{_atoi(G.Cutrfile3) + 2100}］年度に設定しました")

    print("\n予備番号を入力して下さい（３桁）")
    G.Cutrfile4 = scan.s()                # char Cutrfile4[4]

    G.Sifile = "100"

    if G.Saimu == 0:
        G.Saimushu = ""                   # Saimushu[0] = '\0'
    elif G.Saimu == 1:
        if G.Pslsi == 2 and G.Pslsi2 == 1:
            if G.Psly == 25 and G.Kzn == 1:
                G.Saimushu = "AK"
            else:
                print("現在対応できていない組み合わせです。"
                      f"Saimu={G.Saimu}, Pslsi={G.Pslsi}, "
                      f"Pslsi2={G.Pslsi2}, Kzn={G.Kzn}")
                raise SystemExit(1)
        else:
            print("現在対応できていない組み合わせです。"
                  f"Saimu={G.Saimu}, Pslsi={G.Pslsi}, Pslsi2={G.Pslsi2}")
            raise SystemExit(1)
    elif G.Saimu == 2:
        if G.Pslsi == 2 and G.Pslsi2 == 1:
            if G.Psly == 25 and G.Kzn == 1:
                G.Saimushu = "AJ"
            else:
                print("現在対応できていない組み合わせです。"
                      f"Saimu={G.Saimu}, Pslsi={G.Pslsi}, "
                      f"Pslsi2={G.Pslsi2}, Kzn={G.Kzn}")
                raise SystemExit(1)
        else:
            print("現在対応できていない組み合わせです。"
                  f"Saimu={G.Saimu}, Pslsi={G.Pslsi}, Pslsi2={G.Pslsi2}")
            raise SystemExit(1)

    # main.c:144 Saimushu が "10" のときだけ Saimuski を空にする、という
    # 書き方だが Saimushu に "10" が入る経路は無いので常に複製になる。
    if G.Saimushu != "10":
        G.Saimuski = G.Saimushu
    else:
        G.Saimuski = ""

    G.Tumafile = "00"
    print(f"\n 妻積用ファイル番号を[{G.Tumafile}]に設定しています")

    G.Siencha = ""                        # Siencha[0] = '\0'


def print_number():
    """main.c:159 void print_number(void) の忠実移植。"""
    ctemp = (f"{G.Nfile}-{G.Nkfile}-{G.Wcfile}-{G.Ecfile}-{G.Cutrfile4} "
             f"[{G.Cutrfile1}{G.Cutrfile2}{G.Cutrfile3}], "
             f"Part={G.Flg_Part}, Dmakuro={G.Flg_Dmakuro}, "
             f"Jimu={G.Flg_Jimu}")
    print(f"\n{ctemp} : 妻[{G.Tumafile}]")


def _atoi(s):
    """C の atoi。読める先頭の整数だけを取り、読めなければ 0。"""
    i = 0
    n = len(s)
    while i < n and s[i] in " \t\n\r\f\v":
        i += 1
    j = i
    if j < n and s[j] in "+-":
        j += 1
    k = j
    while k < n and s[k].isdigit() and s[k].isascii():
        k += 1
    if k == j:
        return 0
    return int(s[i:k])


if __name__ == "__main__":
    sys.exit(main())
