# -*- coding: utf-8 -*-
"""
プログラム/分布推計/prog03.cpp の忠実移植
=========================================
CSV の読み取り。`func03a` が1行をカンマで割り、`func03b` がファイルを
2次元の文字列リストにする。

原本の癖をそのまま残しているところ — ここが一番の罠
----------------------------------------------------
`func03a` は区切り文字が**1つも無い行で、フィールドを2回返す**。

原本（prog03.cpp:6-20）

    int var03a1 = 0;
    int var03a2 = arg03a1.find_first_of(arg03a2);   // 見つからないと npos
    while (var03a1 < arg03a1.size()) {
      std::string subStr(arg03a1, var03a1, var03a2 - var03a1);
      vector03a1.push_back(subStr);
      var03a1 = var03a2 + 1;
      var03a2 = arg03a1.find_first_of(arg03a2, var03a1);
      if (var03a2 == std::string::npos) { var03a2 = arg03a1.size(); }
    }

`find_first_of` は見つからないと `npos`（`size_t` の最大値）を返すが、
**`int var03a2` に入れている**ので -1 になる。"abc" を渡すと

    1回目  var03a2 = -1  → subStr("abc", 0, -1-0) は長さが (size_t)(-1) に
                           なって末尾までに丸められ "abc"。
                           var03a1 = -1 + 1 = 0
                           var03a2 = find(',', 0) = npos → int -1
                           `-1 == npos` は int が size_t に格上げされて **真**
                           → var03a2 = 3
    2回目  0 < 3 なので subStr("abc", 0, 3) = "abc" を**もう一度** push
                           var03a1 = 3 + 1 = 4
    3回目  4 < 3 が偽で終了

で `["abc", "abc"]` が返る。カンマが1つでもあれば普通に分割される。

つまり**カンマを含まない行だけ、最初のフィールドが2つに増える**。
この癖を写さないと、そういう行を含むファイルで列数が変わる。

そのほか
--------
- `func03b` は先頭 `arg03b2` 行を読み飛ばしてから読む。読み飛ばしの途中で
  EOF になったら打ち切る。
- **空行に出会ったらそこで読むのをやめる**（`if(var03b2.size() == 0) break;`）。
  ファイルの途中に空行があれば以降は読まない。
- ファイルが開けなければ**空のリストを返す**（エラーにしない）。
- `std::getline` は `\n` を取るが `\r` は残す。データが CRLF なら各行の
  末尾に `\r` が付いたまま `std::stod` に渡ることになる（原本どおり）。
"""

__all__ = ["func03a", "func03b"]


def func03a(arg03a1, arg03a2):
    """prog03.cpp:6 の忠実移植。1行を区切り文字で割る。

    `arg03a1` は行（str）、`arg03a2` は区切り1文字。
    区切りが1つも無い行では最初のフィールドが2回返る（上の解説）。
    """
    n = len(arg03a1)
    var03a1 = 0
    pos = arg03a1.find(arg03a2)
    # C の `int var03a2 = arg03a1.find_first_of(...)`。npos は -1 になる
    var03a2 = pos if pos >= 0 else -1
    out = []
    while var03a1 < n:
        # std::string subStr(s, pos, count)。count が負だと (size_t) で
        # 巨大になり、末尾までに丸められる
        count = var03a2 - var03a1
        if count < 0:
            out.append(arg03a1[var03a1:])
        else:
            out.append(arg03a1[var03a1:var03a1 + count])
        var03a1 = var03a2 + 1
        pos = arg03a1.find(arg03a2, var03a1) if var03a1 >= 0 else -1
        var03a2 = pos if pos >= 0 else -1
        if var03a2 == -1:
            # 原本の `var03a2 == std::string::npos` は int -1 が size_t に
            # 格上げされて真になる
            var03a2 = n
    return out


def func03b(arg03b1, arg03b2):
    """prog03.cpp:22 の忠実移植。CSV を2次元の文字列リストで返す。

    `arg03b1` はパス、`arg03b2` は読み飛ばす行数。
    開けなければ空リスト。空行で打ち切る。
    """
    try:
        # 原本は std::ifstream。バイト列で読んで、`\n` だけを行区切りに
        # するために universal newline を切る（`\r` を残す）。
        with open(arg03b1, "rb") as f:
            raw = f.read()
    except OSError:
        return []

    # std::getline(is, s) は '\n' を区切りにして '\n' を捨てる。'\r' は残る。
    # 数値は ASCII なので latin-1（バイト透過）で扱う。
    text = raw.decode("latin-1")
    lines = text.split("\n")
    # 末尾が '\n' で終わっていると最後に空要素ができる。getline は EOF で
    # 止まるので、その空要素は「読めなかった」に相当する。ただし空行として
    # 打ち切り条件に当たるだけなので、そのまま残しておいてよい。

    i = 0
    for _ in range(arg03b2):
        if i >= len(lines):
            break                      # 原本の `if(var03b1.eof()) break;`
        i += 1

    out = []
    while i < len(lines):
        ln = lines[i]
        i += 1
        if len(ln) == 0:
            break                      # 空行で打ち切る
        out.append(func03a(ln, ","))
    return out
