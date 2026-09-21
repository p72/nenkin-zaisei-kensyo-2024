# -*- coding: utf-8 -*-
"""
国民年金/cntl.c の忠実移植（引数15個を読む）
=============================================
63 行。③は標準入力ではなく**コマンド行の引数15個**で設定を受ける
（④基礎年金と同じ流儀。②⑤⑥は標準入力）。

    argv[1]   入力ファイルリスト
    argv[2]   出力ファイルリスト
    argv[3]   国年の試算番号
    argv[4]   経済前提の番号
    argv[5]   外枠の番号
    argv[6]   出生率のファイル（1文字）
    argv[7]   死亡率のファイル（1文字）
    argv[8]   過去債務（0 通常 / 1 過去分 / 2 受給者分）
    argv[9]   賃金スライド
    argv[10]  適用拡大
    argv[11]  適用拡大の年度
    argv[12]  オプション（1 なら基礎45年化）
    argv[13]  オプションの開始年度
    argv[14]  引き上げの間隔（年）
    argv[15]  従来の外枠の番号

`argc != 16` なら `exit(1)`。

`Kako_Saimu` で試算番号に印を付ける
----------------------------------
```c
Kako_Saimu = atoi( argv[8] );
if( Kako_Saimu == 0 )      { strcpy( KOKUNEN , argv[3] );                   Jyukyusha_Nomi = 0; }
else if( Kako_Saimu == 1 ) { sprintf( KOKUNEN , "%s%s", argv[3] , KAKO   ); Jyukyusha_Nomi = 0; }
else if( Kako_Saimu == 2 ) { sprintf( KOKUNEN , "%s%s", argv[3], KAKO_J );
                             Kako_Saimu = 1; Jyukyusha_Nomi = 1; }
```

`KAKO` は `"AK"`、`KAKO_J` は `"AJ"`。試算番号が4桁なら
`KOKUNEN` は `"3001AK"` の6文字＋NUL で `char[7]` にちょうど収まる。
**5桁を渡すと配列の外に出る**（`検証/原本の不具合.md` C の仲間）。

`Kako_Saimu` が 0・1・2 以外だと `KOKUNEN` に**何も入らない**
（`else` が無い）。グローバルなので空文字列のまま `Version` を
組み立て、`file_open` が開くファイル名が狂う。

`Version` の組み立て
--------------------
```c
sprintf( Version , "%s-%s-%s" , KOKUNEN , ECON , SOTOWAKU );
```

`char Version[20]`。`"3001AK-3001-3001"` で16文字＋NUL なので入る。

直書きの2つ
-----------
```c
Kugiri_Nendo = 2024;
Kisai_Shitasasae = 0.80;
```

`Kugiri_Nendo`（2024年度で区切る）と `Kisai_Shitasasae`（既裁定の
下支え 80%）は引数ではなく**ここに直書き**。
"""
from setconst import KAKO, KAKO_J

__all__ = ["cntl", "NatArgError"]

_HIKISU = 15


class NatArgError(Exception):
    """原本が `exit(1)` する引数の渡し方。"""


def cntl(G, argv):
    """cntl.c:14 の忠実移植。`argv` は原本と同じ並び（`argv[0]` は名前）。"""
    if len(argv) != _HIKISU + 1:
        raise NatArgError("入力された引数が異なります。")

    G.Kako_Saimu = int(argv[8])
    if G.Kako_Saimu == 0:
        G.KOKUNEN = argv[3]
        G.Jyukyusha_Nomi = 0
    elif G.Kako_Saimu == 1:
        G.KOKUNEN = "%s%s" % (argv[3], KAKO)
        G.Jyukyusha_Nomi = 0
    elif G.Kako_Saimu == 2:
        G.KOKUNEN = "%s%s" % (argv[3], KAKO_J)
        G.Kako_Saimu = 1
        G.Jyukyusha_Nomi = 1
    # 原本はここに `else` が無い。0・1・2 以外だと KOKUNEN は空のまま

    # `char KOKUNEN[7]` に収まるか（原本は溢れても書き込む）
    if len(G.KOKUNEN) > 6:
        raise NatArgError(
            "KOKUNEN が %d 文字（`char[7]` に入らない）。原本は"
            "配列の外に書き込む: %r" % (len(G.KOKUNEN), G.KOKUNEN))

    G.ECON = argv[4]
    G.SOTOWAKU = argv[5]
    G.BIRTHFILE = argv[6]
    G.DEATH = argv[7]
    G.TINSURA = int(argv[9])
    G.Part = int(argv[10])
    G.Part_Year = int(argv[11])
    G.Option = int(argv[12])
    G.OPTION_START = int(argv[13])
    G.OP_HIKIAGE_KANKAKU = int(argv[14])
    G.SOTOWAKU_JURAI = argv[15]

    G.Version = "%s-%s-%s" % (G.KOKUNEN, G.ECON, G.SOTOWAKU)
    if len(G.Version) > 19:
        raise NatArgError(
            "Version が %d 文字（`char[20]` に入らない）。原本は"
            "配列の外に書き込む: %r" % (len(G.Version), G.Version))

    G.Kugiri_Nendo = 2024

    G.Kisai_Shitasasae = 0.80
