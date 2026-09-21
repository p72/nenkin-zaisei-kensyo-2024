# -*- coding: utf-8 -*-
"""
基礎年金/file_open.c の忠実移植（ファイルリストを読んで開く）
==============================================================
④は入出力のパスをソースに埋めず、**引数で渡した CSV の一覧**から開く。
①⑤⑥はパスをソースに書いていたので、そこだけ作りが違う。

    ファイル番号,読み込みの有無,ディレクトリ,ファイル名,オープンモード

1行目は見出しなので読み捨てる（`file_get` の最初の `read_str`）。
「読み込みの有無」は 0/1 のほかに B・C・D の3つを取る。

    B → `CUT_KOTEI == 1` なら開く（カット率固定のとき読む cuta ファイル）
    C → `kako >= 1`     なら開く（過去債務推計のとき読む cuta ファイル）
    D → `TOUGOU == 1`   なら開く（調整期間一致のとき書く provide ファイル）

ファイル名の中の `{...}` は `chg_str` で置き換える。置換の順番は原本の
とおり。`{Version}` は `{HIYOUSYADATA}` などを組み合わせた文字列なので、
先に個別の名前を置き換えても `{Version}` は残る（`{` `}` 込みで探すため）。

原本の癖をそのまま残しているところ
----------------------------------
1. **`digit_chk` が空文字列に 1 を返す。**`for( i = 0 ; i < strlen(...) )`
   なので 0 文字なら1回も回らず `return 1`。そのあと `atoi("")` が 0 を
   返すので、番号の欠けた行は**ファイル番号 0 として開かれる**。
   同梱の一覧に空欄は無いので起きない。（`検証/原本の不具合.md`）

2. **`digit_chk` が `isdigit` に `char` をそのまま渡す。**非 ASCII の
   バイト（EUC-JP の見出しなど）を渡すと負の `int` になり未定義動作。
   1行目は読み捨てるので実際には届かない。

3. **`cnt` はエラーメッセージのためだけ。**

4. **`fp_io[number]` の範囲を確かめていない。**一覧に 23 以上の番号が
   あれば配列の外に書く。移植版は範囲外を例外にする。
"""
import os
import sys

from cnum import CsvError, ReadStr, chg_str
from glva import G
from setconst import DATA_MAX, KAKO

__all__ = ["file_open"]

NUM_COLUMN = 0
READ_WRITE_COLUMN = 1
DIR_COLUMN = 2
FILE_COLUMN = 3
MODE_COLUMN = 4


def _digit_chk(s):
    """file_open.c:133。全部数字なら 1。**空文字列でも 1**（癖 1.）。"""
    for ch in s:
        if not ("0" <= ch <= "9"):
            return 0
    return 1


def file_open(file_list, fp_io, file_name):
    """file_open.c:21 の忠実移植。

    `fp_io` は `G.fp_in` か `G.fp_out`（list）、`file_name` は
    `G.infile_name` か `G.outfile_name`。どちらを渡したかで
    入力（`ReadStr`）と出力（テキストファイル）を作り分ける。
    """
    if not os.path.exists(file_list):
        print("ファイルリストのオープンに失敗しました (%s)" % file_list)
        sys.exit(1)

    fp = ReadStr(file_list)
    _file_get(fp, fp_io, file_name)
    return


def _file_get(fp, fp_io, file_name):
    """file_open.c:41 の忠実移植。"""
    buffer = [""] * DATA_MAX
    cnt = 0

    # 1行目（見出し）を読み捨てる
    fp.read_str(buffer)

    while True:
        rc, _ = fp.read_str(buffer)
        if rc == -1:      # EOF
            break
        cnt += 1

        rw = buffer[READ_WRITE_COLUMN]

        if rw == "B":
            if G.CUT_KOTEI == 1:
                rw = "1"
            elif G.CUT_KOTEI == 0:
                rw = "0"

        if rw == "C":
            if G.kako == 1 or G.kako == 2:
                rw = "1"
            elif G.kako == 0:
                rw = "0"

        if rw == "D":
            if G.TOUGOU == 1:
                rw = "1"
            elif G.TOUGOU == 0:
                rw = "0"

        # 原本の `atoi( buffer[READ_WRITE_COLUMN] ) == 1`
        if _atoi(rw) != 1:
            continue

        if _digit_chk(buffer[NUM_COLUMN]) == 0:
            print("%d番目のファイルリストが取得できません。" % cnt)
            sys.exit(1)

        number = _atoi(buffer[NUM_COLUMN])
        if not 0 <= number < len(fp_io):
            raise CsvError(
                f"file_open: ファイル番号 {number} は配列の外"
                f"（0〜{len(fp_io) - 1}）。原本は範囲を見ていない（癖 4.）")

        name = buffer[DIR_COLUMN] + buffer[FILE_COLUMN]

        name = chg_str(name, "{HIYOUSYADATA}", G.HIYOUSYADATA)
        name = chg_str(name, "{KOKUNENDATA}", G.KOKUNENDATA)
        name = chg_str(name, "{ECON}", G.ECON)
        name = chg_str(name, "{SOTOWAKU}", G.SOTOWAKU)
        name = chg_str(name, "{SOTOWAKU_CUT}", G.SOTOWAKU_CUT)
        name = chg_str(name, "{Version}", G.Version)
        name = chg_str(name, "{Version_cut}", G.Version_cut)
        name = chg_str(name, "{Version_Jurai}", G.Version_Jurai)
        name = chg_str(name, "{KAKO}", KAKO)
        name = chg_str(name, "{YOBI}", G.YOBI)

        file_name[number] = name
        mode = buffer[MODE_COLUMN]

        try:
            if mode.startswith("r"):
                fp_io[number] = ReadStr(name)
            else:
                # 原本の `fopen( ... , "w" / "a" )`。
                # 日本語の見出しは原本（UTF-8 に変換した木）と同じ
                # バイト列を書くので UTF-8 で開く
                fp_io[number] = open(name, mode[0] + "t", encoding="utf-8",
                                     newline="\n")
        except OSError:
            print("%sの取得に失敗しました" % name)
            sys.exit(1)

    return


def _atoi(s):
    """C の `atoi`。読めなければ 0。"""
    s = s.lstrip(" \t\n\v\f\r")
    i = 0
    if i < len(s) and s[i] in "+-":
        i += 1
    j = i
    while j < len(s) and "0" <= s[j] <= "9":
        j += 1
    if j == i:
        return 0
    try:
        return int(s[:j])
    except ValueError:
        return 0
