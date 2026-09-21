# -*- coding: utf-8 -*-
"""
基礎年金/cntl.c の忠実移植（コマンドライン引数17個の読み取り）
==============================================================
④は①⑤⑥と違って**標準入力を使わない**。引数17個で全部決まる。

    argv[1]  入力ファイルリスト（infile.csv）
    argv[2]  出力ファイルリスト（outfile.csv）
    argv[3]  厚年（被用者）データ番号   → HIYOUSYADATA
    argv[4]  国年データ番号             → KOKUNENDATA
    argv[5]  経済前提番号               → ECON
    argv[6]  外枠番号                   → SOTOWAKU
    argv[7]  外枠番号（カット用）       → SOTOWAKU_CUT（Option==1 のときだけ）
    argv[8]  予備番号                   → YOBI
    argv[9]  過去分                     → kako（0 通常 / 1 過去債務 / 2 従来）
    argv[10] キャリーオーバー           → CARRY
    argv[11] 名目下限撤廃               → D_MACRO
    argv[12] オプション（基礎45年化）   → Option
    argv[13] オプション開始年度         → OPTION_START
    argv[14] 引上げ間隔                 → OP_HIKIAGE_KANKAKU
    argv[15] 調整期間一致               → TOUGOU
    argv[16] カット率固定               → CUT_KOTEI
    argv[17] カット率一本出し           → CUT_ONE_SHUTU

`argv[7]` は `Option == 1` のときだけ使い、そうでなければ
`SOTOWAKU_CUT = SOTOWAKU` になる。`run_pipeline.sh` は
`"$WAKU" "$WAKU"` と同じ値を2つ渡しているので、どちらでも同じ。

`cntl.c` が決め打ちしている値
-----------------------------
    T_NENDO  = 2120   有限均衡の評価年度
    T_DOAI   = 1      その年度に必要な積立度合
    KAISHI1  = 2023   マクロ経済スライドを効かせ始める年度
    KAISHI2  = 2004   （代入するだけでどこからも読まれない）
    C_NENDO  = 2004   調整開始年度の前年
    D_M_NENDO     = 2025   名目下限撤廃を効かせ始める年度
    MARUME_NENDO  = 2025   価格・保険料を丸める最後の年度

原本の癖をそのまま残しているところ
----------------------------------
1. **`KAISHI2` はどこからも読まれない。**`cntl.c:93` で 2004 を入れる
   だけ。（`検証/原本の不具合.md`）

2. **`KOKKONASHI` はどこにも代入されない。**`option.h` で宣言されて
   いるが `cntl.c` は触らないので 0 のまま。読む側も無い。

3. **`Version_tumatumi` も同じく宣言だけ。**

4. **`char` 配列の寸法がぎりぎり。**`HIYOUSYADATA[7]` に
   `sprintf( "%s%s" , "AK" , argv[3] )` と書くので、`argv[3]` が
   5文字以上ならあふれる。試算番号は4桁なので `"AK3001"` + NUL = 7 で
   ちょうど収まる。`YOBI[4]` も3桁＋NUL でちょうど。
   （`検証/原本の不具合.md`）

5. **`kako` が 0・1・2 以外だと `HIYOUSYADATA` が空のまま進む。**
   `else` が無い。移植版は原本と同じく空文字のまま進める。
"""
import sys

from cnum import CsvError
from glva import G
from setconst import KAKO, KAKO_J

__all__ = ["cntl"]

HIKISU = 17


def _fit(name, s, size):
    """原本の `char name[size]` に収まるか（癖 4.）。

    収まらなければ原本は配列の外に書く。黙って違う結果を出さないよう
    ここで落とす。
    """
    if len(s) + 1 > size:
        raise CsvError(
            f"cntl: {name}[{size}] に {s!r}（{len(s)}文字＋NUL）は入らない"
            "（原本は配列の外に書き込む）")
    return s


def cntl(argv):
    """cntl.c:15 の忠実移植。`argv` は原本と同じく `argv[0]` 込みの list。"""
    print("argc=%d" % len(argv))

    if len(argv) != HIKISU + 1:
        print("入力された引数が異なります。")
        sys.exit(1)

    G.kako = int(argv[9])

    if G.kako == 0:
        G.HIYOUSYADATA = _fit("HIYOUSYADATA", argv[3], 7)
        G.KOKUNENDATA = _fit("KOKUNENDATA", argv[4], 7)
    elif G.kako == 1:
        G.HIYOUSYADATA = _fit("HIYOUSYADATA", KAKO + argv[3], 7)
        G.KOKUNENDATA = _fit("KOKUNENDATA", argv[4] + KAKO, 7)
        G.HIYOUSYADATA_Jurai_KAKO = _fit("HIYOUSYADATA_Jurai_KAKO",
                                         argv[3], 7)
        G.KOKUNENDATA_Jurai_KAKO = _fit("KOKUNENDATA_Jurai_KAKO", argv[4], 7)
    elif G.kako == 2:
        G.HIYOUSYADATA = _fit("HIYOUSYADATA", KAKO_J + argv[3], 7)
        G.KOKUNENDATA = _fit("KOKUNENDATA", argv[4] + KAKO_J, 7)
        G.HIYOUSYADATA_Jurai_KAKO = _fit("HIYOUSYADATA_Jurai_KAKO",
                                         argv[3], 7)
        G.KOKUNENDATA_Jurai_KAKO = _fit("KOKUNENDATA_Jurai_KAKO", argv[4], 7)
    # kako が 0・1・2 以外なら空のまま（癖 5.）

    G.ECON = _fit("ECON", argv[5], 5)
    G.SOTOWAKU = _fit("SOTOWAKU", argv[6], 5)
    G.YOBI = _fit("YOBI", argv[8], 4)
    G.CARRY = int(argv[10])
    G.D_MACRO = int(argv[11])
    G.Option = int(argv[12])
    G.OPTION_START = int(argv[13])
    G.OP_HIKIAGE_KANKAKU = int(argv[14])
    G.TOUGOU = int(argv[15])
    G.CUT_KOTEI = int(argv[16])
    G.CUT_ONE_SHUTU = int(argv[17])

    if G.Option == 1:
        G.SOTOWAKU_CUT = _fit("SOTOWAKU_CUT", argv[7], 5)
    else:
        G.SOTOWAKU_CUT = G.SOTOWAKU

    G.Version = _fit("Version", "%s-%s-%s-%s" % (
        G.HIYOUSYADATA, G.KOKUNENDATA, G.ECON, G.SOTOWAKU), 24)

    if G.kako >= 1:
        G.Version_Jurai = _fit("Version_Jurai", "%s-%s-%s-%s" % (
            G.HIYOUSYADATA_Jurai_KAKO, G.KOKUNENDATA_Jurai_KAKO,
            G.ECON, G.SOTOWAKU), 20)

    G.Version_cut = _fit("Version_cut", "%s-%s" % ("1120", G.YOBI), 10)

    G.T_NENDO = 2120
    G.T_DOAI = 1

    if G.CARRY == 1:
        G.Kurikoshim = 1
    else:
        G.Kurikoshim = 0

    G.D_M_NENDO = 2025

    G.KAISHI1 = 2023
    G.KAISHI2 = 2004        # 癖 1. どこからも読まれない
    G.C_NENDO = 2004

    G.MARUME_NENDO = 2025

    return
