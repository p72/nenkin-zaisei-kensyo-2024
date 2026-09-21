# -*- coding: utf-8 -*-
"""
国民年金/file_open.c の忠実移植（ファイルリストを読んで開く）
==============================================================
98 行。`main.c` が2回呼ぶ。

    file_open( argv[1] , fp_in  , infile_name );    入力86本
    file_open( argv[2] , fp_out , outfile_name );   出力11本

リストの形（先頭1行は見出しとして読み捨てる）
---------------------------------------------
```
番号,読む/読まない,ディレクトリ,ファイル名,モード
0,1,../io_file/,econ-{ECON}.csv,r
```

| 列 | 意味 |
|---|---|
| 0 `NUM_COLUMN` | `fp_io[]` の添字 |
| 1 `READ_WRITE_COLUMN` | **1 なら開く**、それ以外は飛ばす |
| 2 `DIR_COLUMN` | ディレクトリ |
| 3 `FILE_COLUMN` | ファイル名（`{…}` を差し替える） |
| 4 `MODE_COLUMN` | `fopen` のモード（`r` / `w`） |

差し替える印は8つ
-----------------
```c
chg_str( file_name[number] , "{KOKUNEN}" , KOKUNEN );
chg_str( file_name[number] , "{ECON}" , ECON );
chg_str( file_name[number] , "{SOTOWAKU}" , SOTOWAKU );
chg_str( file_name[number] , "{SOTOWAKU_JURAI}" , SOTOWAKU_JURAI );
chg_str( file_name[number] , "{Version}" , Version );
chg_str( file_name[number] , "{KAKO}" , KAKO );
chg_str( file_name[number] , "{BIRTHFILE}" , BIRTHFILE );
chg_str( file_name[number] , "{DEATH}" , DEATH );
```

**順番に意味がある。** `{SOTOWAKU}` を先に替えるので、
`{SOTOWAKU_JURAI}` は……**替わらない**。`{SOTOWAKU}` は
`{SOTOWAKU_JURAI}` の**部分文字列ではない**（`{` と `}` で
囲まれているため `"{SOTOWAKU}"` は `"{SOTOWAKU_JURAI}"` に
含まれない）ので、実際には取り違えは起きない。
`{Version}` も `{KOKUNEN}-{ECON}-{SOTOWAKU}` に展開済みの
`Version` を入れるので、先に `{KOKUNEN}` を替えても影響しない。

最後の行が落ちる
----------------
```c
read_str( buffer , fp , &data_number );          /* 見出しを捨てる */
cnt = 0;
while( read_str( buffer , fp , &data_number ) != EOF ) { … }
```

`read_str` は **EOF に当たった呼び出しでも欄を埋める**が、
`while` の条件が偽になるので**その行は処理されない**。
リストの最後が改行で終わっていれば、最後の改行のあとの
呼び出しが EOF を返すので問題ない。**改行で終わっていないと
最後の1本が黙って開かれない**（`検証/原本の不具合.md` の
新しい項）。

そのとき `read_str` は `previous_c` を未初期化で読む（B4 の仲間）。

`digit_chk` は空文字列を通す
----------------------------
```c
for( i = 0 ; i < strlen( digit_str ) ; i++ )
  if( isdigit( digit_str[i] ) == 0 ) return 0;
return 1;
```

`strlen` が 0 なら**ループが1回も回らずに 1 を返す**。
番号の欄が空の行があると `atoi("")` = 0 で `fp_io[0]` を
上書きする。同梱のリストには空行が無いので起きない。

文字の符号化
------------
原本は `fgetc` でバイトを読み、`fprintf` でバイトを書く。
入力の CSV は **EUC-JP**（見出しだけ日本語。数値とパスは ASCII）
なので、読むほうは **latin-1（バイト透過）**で開く。書くほうは
原本のソースに入っている日本語の見出しをそのまま出すので、
**UTF-8 に変換した原本**と同じバイト列になるよう UTF-8 で開く
（④基礎年金の移植と同じ扱い）。

`buffer` を使い回す
-------------------
`buffer` は `file_open` の局所（`char buffer[DATA_MAX][BUFFER_MAX]`、
**初期化なし**）で、`read_str` は読めた欄だけ書き換える。列が
5つ未満の行があると `buffer[MODE_COLUMN]` に**前の行の値**
（または未初期化のごみ）が残る。同梱のリストは全行5列。
"""
import os

from setconst import BUFFER_MAX, DATA_MAX, KAKO
from stdfm import EOF, Buffer, NatError, chg_str, read_str

__all__ = ["file_open", "file_close", "digit_chk"]

_NUM_COLUMN = 0
_READ_WRITE_COLUMN = 1
_DIR_COLUMN = 2
_FILE_COLUMN = 3
_MODE_COLUMN = 4


def digit_chk(digit_str):
    """file_open.c:84 の忠実移植。**空文字列は 1 を返す**。"""
    for ch in digit_str:
        if not ("0" <= ch <= "9"):
            return 0
    return 1


def _c_atoi(s):
    """C の `atoi`。読めなければ 0。"""
    s = s.lstrip(" \t\n\v\f\r")
    i = 0
    if i < len(s) and s[i] in "+-":
        i += 1
    j = i
    while j < len(s) and s[j].isdigit():
        j += 1
    if j == i:
        return 0
    return int(s[:j])


def file_open(G, file_list, fp_io, file_name, base=""):
    """file_open.c:17 の忠実移植。

    `base` はリストの中の相対パスを解く起点（原本は
    `nat/` から起動する前提の相対パス）。
    """
    try:
        # 原本は `fgetc` でバイトを読む。リストは EUC-JP の見出しを
        # 持つが、使う欄（番号・旗・パス・モード）は ASCII なので
        # **latin-1（バイト透過）**で開く
        fp = open(os.path.join(base, file_list), "r",
                  encoding="latin-1", newline="")
    except OSError:
        raise NatError("ファイルリストのオープンに失敗しました (%s)"
                       % file_list)

    with fp:
        buf = Buffer(DATA_MAX)

        read_str(buf, fp)               # 見出しを1行捨てる

        cnt = 0

        while read_str(buf, fp) != EOF:
            cnt += 1

            if _c_atoi(buf.str[_READ_WRITE_COLUMN]) == 1:
                if digit_chk(buf.str[_NUM_COLUMN]) == 0:
                    raise NatError(
                        "%d番目のファイルリストが取得できません。" % cnt)

                number = _c_atoi(buf.str[_NUM_COLUMN])
                if not 0 <= number < len(fp_io):
                    raise NatError(
                        "%d番目のファイルリストの番号が %d。`fp_io[%d]` の"
                        "外。原本は未定義動作" % (cnt, number, len(fp_io)))

                name = "%s%s" % (buf.str[_DIR_COLUMN],
                                 buf.str[_FILE_COLUMN])

                # 差し替える順も原本のまま
                name = chg_str(name, "{KOKUNEN}", G.KOKUNEN)
                name = chg_str(name, "{ECON}", G.ECON)
                name = chg_str(name, "{SOTOWAKU}", G.SOTOWAKU)
                name = chg_str(name, "{SOTOWAKU_JURAI}", G.SOTOWAKU_JURAI)
                name = chg_str(name, "{Version}", G.Version)
                name = chg_str(name, "{KAKO}", KAKO)
                name = chg_str(name, "{BIRTHFILE}", G.BIRTHFILE)
                name = chg_str(name, "{DEATH}", G.DEATH)

                if len(name) > BUFFER_MAX - 1:
                    raise NatError(
                        "ファイル名が %d 文字（`char[%d]` に入らない）。"
                        "原本は配列の外に書き込む: %r"
                        % (len(name), BUFFER_MAX, name))

                file_name[number] = name

                mode = buf.str[_MODE_COLUMN]
                try:
                    if mode.startswith("r"):
                        # 読むほうは原本と同じくバイト透過
                        enc = "latin-1"
                    else:
                        # 書くほうは原本（UTF-8 に変換した木）と同じ
                        # バイト列になるよう UTF-8
                        enc = "utf-8"
                    fp_io[number] = open(os.path.join(base, name), mode,
                                         encoding=enc, newline="")
                except OSError:
                    raise NatError("%sの取得に失敗しました" % name)


def file_close(G):
    """`snaps.h:149` の `file_close()`。**原本には定義が無い**。

    `snaps.h` は宣言しているが、16本の .c のどこにも定義が無く、
    `main.c` も呼ばない。リンクは通る（呼ばないので）。
    出力は `main()` を抜けるときに OS が閉じる。
    `検証/原本の不具合.md` の F を参照。

    移植版は Python なので明示的に閉じる。原本と違うが、
    **出力の中身は変わらない**（`fflush` されるだけ）。
    """
    for lst in (G.fp_in, G.fp_out):
        for i, fp in enumerate(lst):
            if fp is not None:
                fp.close()
                lst[i] = None
