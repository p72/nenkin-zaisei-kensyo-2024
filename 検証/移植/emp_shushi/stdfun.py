# -*- coding: utf-8 -*-
"""
プログラム/厚生年金/収支計算/stdfun.c の忠実移植
=================================================
CSV の読み取りと丸め。丸め（nround）は cnum.py に置いてあるので、ここは
レコード分解とヘッダ読み飛ばしだけ。

原本の癖をそのまま残しているところ
----------------------------------
`rd_drec()` はフィールドを **',' か '\\n' に出会った時にだけ確定する**。
つまり行末に改行もカンマも無い場合、**最後のフィールドは捨てられる**。
原本は fgets() で読むので通常は '\\n' が付いているが、ファイル末尾の
最終行に改行が無いとその行の最後の値が落ちる。移植でもそう振る舞う。

値の代入が範囲検査より**先**に来ているのも原本のまま（stdfun.c:26-34）。
num_data 個目に達したときはいったん ddata[num_data] に書いてから
エラー終了する。C では配列の外に1個書く未定義動作だが、直後に exit(1)
するので観測できる違いは出ない。移植では代入を試みてから同じ条件で
SystemExit する。
"""
from cnum import c_atof

__all__ = ["rd_drec", "rd_crec", "strncpy2", "rd_header"]


def rd_drec(rec, ddata, num_data):
    """stdfun.c:14 の忠実移植。

    rec を ',' / '\\n' で区切って atof した値を ddata に詰め、確定した
    フィールド数を返す。ddata は呼び出し側が用意した長さ num_data の list
    （原本の `double dtemp[7]` に相当）。

    戻り値は num_comma。原本の変数名をそのまま使っている。
    """
    i = j = 0
    num_comma = 0
    ctemp = []                       # 原本の char ctemp[102]

    n = len(rec)
    while i < n and rec[i] != "\0":
        ch = rec[i]
        if ch == "," or ch == "\n":
            # 原本は代入が先、範囲検査が後
            val = c_atof("".join(ctemp))
            if num_comma < len(ddata):
                ddata[num_comma] = val
            if num_comma < num_data:
                num_comma += 1
                j = 0
                ctemp = []
                i += 1
            else:
                print(f"rd_drec()が読み込み可能データ数を超えています。[{rec}]")
                raise SystemExit(1)
        else:
            ctemp.append(ch)
            j += 1
            i += 1
            if j > 100:              # 原本 stdfun.c:39 char ctemp[102]
                print("読み込みデータの桁数がrd_drec()内のバッファー以上です。")
                raise SystemExit(1)

    return num_comma


def rd_crec(rec, len_cdata, loca):
    """stdfun.c:49 の忠実移植。loca 番目のフィールドを文字列で返す。

    原本は `void rd_crec(char *rec, char *cdata, int len_cdata, int loca)` で
    cdata に書き込むが、移植では戻り値にした（Python に out 引数が無いため）。
    桁数超過とフィールド不足のときの exit(1) はそのまま。

    ⑤の中では呼ばれていない（①〜④で使われている共通部品）。
    """
    i = j = 0
    num_comma = 0
    ctemp = []

    n = len(rec)
    while i < n and rec[i] != "\0":
        ch = rec[i]
        if ch == "," or ch == "\n":
            num_comma += 1
            s = "".join(ctemp)
            if num_comma == loca:
                if j < len_cdata:
                    return s
                print("rd_crec:投入データの桁数が代入用変数のサイズを"
                      f"超えています。[{s}]")
                raise SystemExit(1)
            else:
                j = 0
                ctemp = []
                i += 1
        else:
            ctemp.append(ch)
            j += 1
            i += 1
            if j > 100:
                print("読み込みデータの桁数がrd_crec()内のバッファー以上です。")
                raise SystemExit(1)

    print("rd_crec:データがありませんでした。")
    raise SystemExit(1)


def strncpy2(istr, sh, length):
    """stdfun.c:89 の忠実移植。

        void strncpy2(char *ostr, char *istr, int sh, int len){
            sh--;
            for(i=0; i<len; i++) ostr[i] = istr[i-sh];

    添字が `istr[i-sh]` になっている。sh は 1 減らされているので、sh が 2 以上
    だと **i=0 のとき istr[-1] を読む**（配列の手前を読む未定義動作）。
    意図はおそらく `istr[i+sh]` で、原本のまま残すと再現できない。

    ⑤の中では呼ばれていないので、移植では未実装のまま置く。呼ばれたら
    気付けるように例外にしてある（①〜④の移植時に、その使い方を見てから
    決める）。
    """
    raise NotImplementedError(
        "stdfun.c:89 strncpy2 は添字が istr[i-sh] で、sh>=2 のとき配列の手前を"
        "読む（原本の不具合と思われる）。⑤では未使用。使う箇所が出てきたら"
        "そこでの実挙動を確かめてから移植する。")


def rd_header(fp):
    """stdfun.c:98 の忠実移植。

    '#' で始まる行を探し、`#<制度>-<システム>-<情報>` の制度が 99 になる行まで
    読み飛ばす。見つからなければエラー終了。

    fp は行を返すイテレータ（テキストモードのファイルオブジェクト）。
    原本は fgets(char_buffer, 499, fp) なので **1行 499 バイトで切られる**が、
    ヘッダ行はそれより短いので影響しない。
    """
    Done = 0

    for char_buffer in fp:
        if char_buffer[:1] == "#":
            # sscanf(char_buffer, "#%d-%d-%d", &seido, &system, &jouhou)
            seido = _sscanf_head_int(char_buffer)
            if seido == 99:
                Done = 1
                break
        if Done:
            break

    if Done == 0:
        print("うまくファイルが読み込めていません。")
        raise SystemExit(1)


def _sscanf_head_int(s):
    """`sscanf(s, "#%d-%d-%d", ...)` の第1項だけを取り出す。

    '#' の直後から C の %d が読める範囲（符号＋数字列）を読む。読めなければ
    sscanf は変数を書き換えないので、原本では seido が前の値のまま残る。
    原本は seido を while の外で初期化していない自動変数なので、'#' 行の
    数字が読めない場合の値は不定になる。実データのヘッダは必ず
    `#99-...` の形なので、移植では「読めなければ一致しない」と扱う。
    """
    i = 1
    n = len(s)
    while i < n and s[i] in " \t":
        i += 1
    j = i
    if j < n and s[j] in "+-":
        j += 1
    k = j
    while k < n and s[k].isdigit() and s[k].isascii():
        k += 1
    if k == j:
        return None
    return int(s[i:k])
