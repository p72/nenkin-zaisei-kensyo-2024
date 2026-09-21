# -*- coding: utf-8 -*-
"""
C の FILE* をバイト単位で模す
=============================
出力をバイト一致させるには、文字列ではなく**バイト列**で扱う必要がある。

理由は `flck.c:49` にある。

    fprintf(ofp01_shushi[i], "%s", char_buffer);

char_buffer は入力ファイル（**EUC-JP**）から fgets で読んだ生のバイト列で、
それをそのまま出力に流している。一方、同じ関数の中の

    fprintf(ofp01_shushi[i], "%s, 予備:, %s, ...", ...)

の「予備:」は**ソースファイルの文字コード**で出る。原本は EUC-JP だが
`検証/実行/run_pipeline.sh` はビルド前に iconv で UTF-8 へ変換するので、
実際に走るバイナリは **UTF-8** を吐く。つまり1つの出力ファイルの中に
EUC-JP（入力から来たヘッダ）と UTF-8（ソース由来のラベル）が混在する。

これを Python の str で扱うと、どちらかに decode した時点で崩れる。そこで

    バイト列 ←→ str の対応を **latin-1** で取る

latin-1 は 0x00〜0xFF を U+0000〜U+00FF に1対1で写すので、
`bytes.decode('latin-1').encode('latin-1')` が恒等写像になる（バイト透過）。
数値の解析や ',' での分割は ASCII 範囲なのでそのまま動く。

ソース由来の日本語リテラルは `u()` で「UTF-8 バイト列の latin-1 表現」に
直してから混ぜる。これで原本のバイナリと同じバイト列が出る。
"""

__all__ = ["CFile", "copen", "u", "SRC_ENCODING"]

# 原本のソースをビルドするときの文字コード。run_pipeline.sh が iconv で
# UTF-8 に変換してからコンパイルするので、実行バイナリの出力は UTF-8。
# EUC-JP のままビルドしたバイナリと比べるときは 'euc_jp' にする。
SRC_ENCODING = "utf-8"


def u(s):
    """ソース由来の文字列（日本語を含む）をバイト透過表現に直す。

    C のソースに書かれた文字列リテラルは、コンパイル時の文字コードの
    バイト列としてそのまま出力される。それを再現する。
    """
    return s.encode(SRC_ENCODING).decode("latin-1")


class CFile:
    """C の FILE* の、この移植で必要な部分だけ。

    行は latin-1 の str として出入りする（1文字 = 1バイト）。
    """

    def __init__(self, path, mode):
        self.path = path
        self.mode = mode
        if "r" in mode:
            self._f = open(path, "rb")
        elif "w" in mode:
            self._f = open(path, "wb")
        elif "a" in mode:
            self._f = open(path, "ab")
        else:
            raise ValueError(f"未対応のモード: {mode}")

    # ---- 読み ----
    def fgets(self, size=None):
        """C の fgets(buf, size, fp)。

        改行を**含めて**返す。EOF なら None（C の NULL）。
        size を渡すと size-1 バイトで切る（C と同じ）。行がそれより長い
        場合、残りは次の fgets で返る。
        """
        line = self._f.readline()
        if not line:
            return None
        if size is not None and len(line) > size - 1:
            # size-1 バイトで切って、残りは読み戻す
            keep, rest = line[:size - 1], line[size - 1:]
            self._f.seek(-len(rest), 1)
            line = keep
        return line.decode("latin-1")

    def __iter__(self):
        """`for rec in fp:` を C の while(fgets(...)) と同じに見せる。"""
        while True:
            line = self.fgets()
            if line is None:
                return
            yield line

    # ---- 書き ----
    def fputs(self, s):
        """latin-1 の str（＝バイト列）をそのまま書く。"""
        self._f.write(s.encode("latin-1"))

    def fprintf(self, s):
        """C の fprintf。書式化は呼び出し側で済ませてから渡す。

        渡す文字列は**バイト透過表現**であること。ソース由来の日本語は
        `u()` を通しておく。
        """
        self.fputs(s)

    def fp(self, s):
        """ソース由来の文字列をそのまま書く（`fprintf(u(s))` の短縮形）。

        `shus_out.c` / `shus_fullout.c` の出力は見出しも数値も**全部が
        ソース由来**（入力から来たバイト列を混ぜる箇所が無い）なので、
        こちらを使う。バイト透過を意識しないといけないのは
        `flck.c` のように入力の生バイト列を流す所だけ。
        """
        self._f.write(s.encode(SRC_ENCODING))

    # ---- その他 ----
    def close(self):
        if self._f is not None:
            self._f.close()
            self._f = None

    def tell(self):
        return self._f.tell()

    def __repr__(self):
        return f"<CFile {self.mode} {self.path}>"


def copen(path, mode):
    """C の fopen。開けなければ None を返す（C と同じ）。"""
    try:
        return CFile(path, mode)
    except OSError:
        return None


def fclose(fp):
    """C の fclose。

    原本には `fclose(NULL)` になる経路がある（`fcls.c:64` の ifp_Touitu は
    通常試算では開かれていない）。glibc では segfault するので
    `検証/実行/patches/glibc-portability.patch` の1つ目のハンクが
    `if(ifp_Touitu != NULL)` を足している。移植では同じ守りを入れる
    （＝パッチ後の挙動に合わせる。パッチは計算結果を変えない）。
    """
    if fp is not None:
        fp.close()
