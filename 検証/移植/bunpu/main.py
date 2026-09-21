# -*- coding: utf-8 -*-
"""
プログラム/分布推計/main.cpp の忠実移植
=======================================
⑥分布推計の入口。標準入力から6つの番号を読み、性別×基準年齢の12通り
（`{1,2} × {17,27,37,47,57,62}`）について、基準年齢から64年度まで
1年ずつ回す。

年度ループの中の順番（`main.cpp:104-225`）
------------------------------------------
これが⑥の全体の流れで、**順番そのものが仕様**。

     1. 遷移表を読む（vector026）と上限の表（vector029）
     2. 2027年度の特例の人数（main_var005）を数える
     3. **新しい人を追加する**（vector026 の末尾から2行目ぶん）
        var008 = 90、var035 = 9 で入る
     4. `std::shuffle(vector023, gen_rand)` で並び順を振り直す
     5. 全員の var002 を並び順に、年齢と年度を1つ進め、
        **var007 = var008**（前年度の状態を当年度に写す）、var037 = 0、
        var039 = var041、var040 = var042
     6. 初年度だけ func10c → func11a（初期値づくり）
     7. **var002 で並べ替え → var007 で並べ替え**
     8. func06a / func06b（2059〜2069年度だけ）
     9. func07a → func07b → func08a（遷移先を決める）
    10. 残りの数の累積（vector035）と総和（main_var007）
    11. **var037 で並べ替え** → func09b（あふれた人に状態を割り当てる）
    12. func09c（月数と年金額の積み上げ）
    13. vector025 を賃金上昇で伸ばす
    14. func10b（等級の割り当て）
    15. func10c（目標値合わせ）→ func10d（年金額）→ func11a（年金額）
    16. 最終年度（64）だけ func12a/b/c で集計

乱数
----
`std::mt19937 gen_rand(0)` は **loop_var002 のループの中**で作られる
（`main.cpp:90`）。つまり**コホートごとに 0 で種まきし直す**。
`clib/cppstd.py` の `MT19937` と `shuffle` が libstdc++ と一致することは
`検証/移植/test_cppstd.py` で確かめてある。

原本の癖をそのまま残しているところ
----------------------------------
1. **`vector014` を読むが一度も使わない**（`main.cpp:51`）
   `func04k`（基礎の改定率 `kaitea-*`）を読み込んで、そのまま捨てている。
   使っているのは `vector015`（`func04m` ＝ 比例の `kaiteb-*`）だけ。
   ファイルが無いと `func04k` の中で `std::exit(1)` するので、
   **「読めること」だけが意味を持つ**。
   （`検証/原本の不具合.md`）

2. **`if (loop_var002 >= 16)` は常に真**（`main.cpp:73`）
   基準年齢は `{17,27,37,47,57,62}`（`main.cpp:38`）なので最小が 17。
   偽なら `main_var002` と `main_var003` が未初期化のまま使われる。

3. **`objects02` を値で持つのでコピーが多発する**
   `std::vector<class02>` に対して `stable_sort` を3回、`push_back` を
   毎年度かけるので、そのたびにコピーコンストラクタが走る
   （`klass.py` の解説 1.）。Python では参照を並べ替えるだけ。

4. **`main_var003` は最大値を取るが、初期値が `objects02[0]` 依存**
   （`main.cpp:80-85`）。人数が0だと範囲外。実データでは起きない。

5. **`vector019`〜`vector021` は最終年度以外は 0 のまま**
   `func12a/b/c` は `loop_var003 == main_var001 - 1`（64）でだけ呼ばれ、
   `func13a/b/c` はそのあと1回だけ書く。
"""
import sys

from cppnum import stod, stoi
from cppstd import MT19937, shuffle
from klass import (STATE_CODES, Class01, Class02, cmp_var002, cmp_var007,
                   cmp_var037)
import prog04 as p4
from prog03 import func03b
from prog05 import func05a
from prog06 import func06a, func06b
from prog07 import func07a, func07b
from prog08 import func08a
from prog09 import func09b, func09c
from prog10 import func10a, func10b, func10c, func10d
from prog11 import func11a
from prog12 import func12a, func12b, func12c
from prog13 import func13a, func13b, func13c

__all__ = ["main", "run"]

# main.cpp:37,38,39
SEXES = [1, 2]
BASE_AGES = [17, 27, 37, 47, 57, 62]
MAIN_VAR001 = 65


class _Scan:
    """`std::cin >> int` の代わり。空白で区切って int を1つずつ返す。"""

    def __init__(self, stream):
        self._it = iter(stream.read().split())

    def d(self):
        return int(next(self._it))


def _read_objects01(scan):
    """main.cpp:13-33。6つの番号を読んで、矛盾があれば exit(1)。"""
    names = ["object01a", "object01b", "object01c", "object01d",
             "object01e", "object01f"]
    o = {}
    for k in names[:2]:
        c = Class01()
        c.input_value001(k, scan)
        o[k] = c
    a = o["object01a"].value001
    b = o["object01b"].value001
    if b >= 1:
        if (a // 100) % 10 != b:
            raise SystemExit(1)
    c = Class01()
    c.input_value001("object01c", scan)
    o["object01c"] = c
    cv = c.value001
    if b == 0:
        # 原本は `!( A && B || C && D )` で && が優先される
        if not (((a // 100) % 10 == 0 and cv == 0)
                or ((a // 100) % 10 == 5 and cv == 1)):
            raise SystemExit(1)
    else:
        if cv == 1:
            raise SystemExit(1)
    for k in names[3:]:
        x = Class01()
        x.input_value001(k, scan)
        o[k] = x
    return o


def run(scan, base=""):
    """main.cpp:12 の忠実移植。`base` は相対パスの基点（既定は原本どおり）。"""
    p4.set_base(base)
    o = _read_objects01(scan)
    a = o["object01a"].value001
    ob = o["object01b"].value001
    oc = o["object01c"].value001
    od = o["object01d"].value001
    oe = o["object01e"].value001
    of = o["object01f"].value001

    # main.cpp:40-49。分布の表8つから加重平均を作る
    v004 = func03b(p4.func04t(a, od, oe), 1)
    v005 = func03b(p4.func04u(a, od, oe), 1)
    v006 = func03b(p4.func04v(a, od, oe), 1)
    v007 = func03b(p4.func04w(a, od, oe), 1)
    v008 = func03b(p4.func04x(a, od, oe), 1)
    v009 = func03b(p4.func04y(a, od, oe), 1)
    v010 = func03b(p4.func04z(a, od, oe), 1)
    v011 = func03b(p4.func04aa(a, od, oe), 1)
    v012 = [[[[0.0] * 55 for _ in range(2)] for _ in range(105)]
            for _ in range(4)]
    func10a(v004, v005, v006, v007, v008, v009, v010, v011, v012)

    v013 = func03b(p4.func04j(oe), 0)
    # **v014 は読むだけで使わない**（癖 1.）。読めることだけが意味を持つ
    func03b(p4.func04k(od, oe), 0)
    v015 = func03b(p4.func04m(od, oe), 0)
    v016 = func03b(p4.func04n(a, od, oe), 250)
    if of == 1:
        v017 = func03b(p4.func04p(a, od, oe), 0)
        v018 = func03b(p4.func04q(a, od, oe), 0)
    else:
        v017 = func03b(p4.func04r(a, od, oe), 0)
        v018 = func03b(p4.func04s(a, od, oe), 0)

    for sex in SEXES:
        for age0 in BASE_AGES:
            _cohort(sex, age0, a, ob, oc, of, v012, v013, v015, v016,
                    v017, v018)


def _cohort(loop_var001, loop_var002, a, ob, oc, of, v012, v013, v015,
            v016, v017, v018):
    """main.cpp:64-229 の1コホート（性別×基準年齢）ぶん。"""
    v019 = [0] * 4
    v020 = [0] * 7
    v021 = [0.0] * 8

    # main.cpp:73-89。`loop_var002 >= 16` は常に真（癖 2.）
    v022 = func03b(p4.func04a(loop_var001, loop_var002), 7)
    main_var002 = len(v022)
    objects02 = [Class02() for _ in range(main_var002)]
    func05a(main_var002, v022, objects02)
    main_var003 = objects02[0].var001
    for i in range(main_var002):
        if objects02[i].var001 > main_var003:
            main_var003 = objects02[i].var001
    v023 = list(range(main_var002))

    # **コホートごとに種 0 でまき直す**（main.cpp:90）
    gen_rand = MT19937(0)

    v024 = func03b(p4.func04i(), 0)
    ncol = len(v024[0]) + 1
    v025 = [[0.0] * ncol for _ in range(len(v024))]
    main_var004 = ((1.0 + stod(v013[22][3]) / 100.0)
                   * (1.0 + stod(v013[22][6]) / 100.0))
    for i in range(len(v025)):
        if i < 275:
            v025[i][0] = 996000.0 / main_var004
        else:
            v025[i][0] = 924000.0 / main_var004
        src = v024[i]
        for j in range(1, ncol):
            v025[i][j] = stod(src[j - 1])

    for loop_var003 in range(loop_var002, MAIN_VAR001):
        v026 = func03b(
            p4.func04b(loop_var001, loop_var002,
                       loop_var003 + 2022 - loop_var002, loop_var003 + 1, a),
            0)
        main_var005 = 0
        # main.cpp:109-129。2027年度の特例の人数
        if ob == 2 or ob == 3 or ob == 4:
            if loop_var003 - loop_var002 == 5:
                v027 = []
                v028 = []
                if a % 10 == 1:
                    v027 = func03b(p4.func04b(
                        loop_var001, loop_var002,
                        loop_var003 + 2022 - loop_var002, loop_var003 + 1,
                        2111), 0)
                    v028 = func03b(p4.func04b(
                        loop_var001, loop_var002,
                        loop_var003 + 2022 - loop_var002, loop_var003 + 1,
                        2311), 0)
                elif a % 10 == 2:
                    v027 = func03b(p4.func04b(
                        loop_var001, loop_var002,
                        loop_var003 + 2022 - loop_var002, loop_var003 + 1,
                        2112), 0)
                    v028 = func03b(p4.func04b(
                        loop_var001, loop_var002,
                        loop_var003 + 2022 - loop_var002, loop_var003 + 1,
                        2312), 0)
                elif a % 10 == 3:
                    v027 = func03b(p4.func04b(
                        loop_var001, loop_var002,
                        loop_var003 + 2022 - loop_var002, loop_var003 + 1,
                        2113), 0)
                    v028 = func03b(p4.func04b(
                        loop_var001, loop_var002,
                        loop_var003 + 2022 - loop_var002, loop_var003 + 1,
                        2313), 0)
                for i in range(len(v027)):
                    main_var005 += stoi(v028[i][11])
                    main_var005 -= stoi(v027[i][11])
                if main_var005 < 0:
                    main_var005 = 0

        # 上限の表を数値に。main.cpp:130-135。
        # 原本の寸法は「行数 × **0行目の列数**」なので、そこに合わせる
        ncol26 = len(v026[0])
        v029 = [[0] * ncol26 for _ in v026]
        for i in range(len(v026)):
            for j in range(len(v026[i])):
                v029[i][j] = stoi(v026[i][j])

        # **新しい人を追加する**。main.cpp:136-152
        tail = v026[len(v026) - 2]
        for j in range(len(tail)):
            nadd = stoi(tail[j])
            if nadd > 0:
                for x in range(main_var002, main_var002 + nadd):
                    newp = Class02()
                    objects02.append(newp)
                    v023.append(x)
                    main_var003 += 1
                    newp.var001 = main_var003
                    newp.var003 = 2021 - loop_var002 + loop_var003
                    newp.var004 = loop_var001
                    newp.var005 = loop_var003
                    newp.var006 = (2021 - loop_var002) * 10000 + 1010
                    newp.var008 = 90
                    newp.var035 = 9
                main_var002 += nadd

        # 並び順を振り直す。main.cpp:153
        shuffle(v023, gen_rand)

        # 1年進める。main.cpp:154-167
        for i in range(main_var002):
            p = objects02[i]
            p.var002 = v023[i]
            p.var003 += 1
            p.var005 += 1
            p.var007 = p.var008          # 前年度の状態を当年度に写す
            p.var037 = 0
            p.var039 = p.var041
            p.var040 = p.var042

        main_var006 = 1056000.0
        if loop_var003 == loop_var002:
            func10c(main_var002, objects02, loop_var001, loop_var002,
                    loop_var002 - 1, v012, ob, main_var006)
            func11a(main_var002, objects02, loop_var001, loop_var002,
                    loop_var002 - 1, v016, v017, v018, v013, oc)

        objects02.sort(key=cmp_var002)
        objects02.sort(key=cmp_var007)

        v030 = [[0] * ncol26 for _ in v026]
        if 59 <= loop_var003 <= 63:
            func06a(main_var002, STATE_CODES, objects02, v026, v030, v029,
                    oc, loop_var002)
        if 64 <= loop_var003 <= 69:
            func06b(loop_var003, main_var002, STATE_CODES, objects02, v026,
                    v030, v029)

        v031 = func03b(p4.func04c(loop_var001, loop_var003), 0)
        v032 = func03b(p4.func04d(loop_var001, loop_var003), 0)
        v033 = func03b(p4.func04e(loop_var001), 0)
        v034 = func03b(p4.func04f(loop_var001, loop_var003), 0)
        func07a(loop_var003, main_var002, STATE_CODES, objects02, v026, v031,
                v030, v029, ob, oc, loop_var002)
        func07b(loop_var003, main_var002, STATE_CODES, objects02, v026, v032,
                v033, v030, v029, ob, oc, loop_var002)
        func08a(main_var002, STATE_CODES, objects02, v026, v034, v030, v029,
                ob)

        # 残りの数の累積。main.cpp:190-197
        v035 = [[0] * ncol26 for _ in v026]
        main_var007 = 0
        for i in range(len(v026)):
            for j in range(len(v026[i])):
                main_var007 += v029[i][j]
                v035[i][j] = main_var007

        objects02.sort(key=cmp_var037)
        func09b(main_var007, v026, v035, STATE_CODES, objects02)
        func09c(main_var002, objects02, oc, loop_var002)

        v036 = func03b(p4.func04g(loop_var001, loop_var003), 0)
        v037 = func03b(p4.func04h(loop_var001, loop_var003), 0)

        # vector025 を賃金上昇で伸ばす。main.cpp:203-207
        r = ((1.0 + stod(v013[loop_var003 - loop_var002 + 21][3]) / 100.0)
             * (1.0 + stod(v013[loop_var003 - loop_var002 + 21][6]) / 100.0))
        for row in v025:
            for j in range(len(row)):
                row[j] = row[j] * r

        func10b(main_var002, objects02, v036, v037, v025, ob, loop_var003,
                loop_var002, main_var005)

        # main.cpp:209-216
        if loop_var003 - loop_var002 <= 2:
            main_var006 = 1056000.0
        else:
            main_var006 = 1056000.0
            for i in range(2025, loop_var003 - loop_var002 + 2022 + 1):
                main_var006 = (main_var006
                               * (1.0 + stod(v013[i - 2001][3]) / 100.0)
                               * (1.0 + stod(v013[i - 2001][6]) / 100.0))

        func10c(main_var002, objects02, loop_var001, loop_var002,
                loop_var003, v012, ob, main_var006)
        func10d(main_var002, objects02, loop_var002, loop_var003, v015)
        func11a(main_var002, objects02, loop_var001, loop_var002,
                loop_var003, v016, v017, v018, v013, oc)

        if loop_var003 == MAIN_VAR001 - 1:
            func12a(main_var002, objects02, v019)
            func12b(main_var002, objects02, v020)
            func12c(main_var002, objects02, v021)

    func13a(loop_var001, loop_var002, a, of, v019)
    func13b(loop_var001, loop_var002, a, of, v020)
    func13c(loop_var001, loop_var002, a, of, v021)


def main(argv=None):
    """`検証/実行/run_bunpu.sh` と同じ使い方。標準入力から6つの番号を読む。

    第1引数に基点（`bunpu/exec` に当たるディレクトリ）を渡せる。
    省略すると原本どおりカレントディレクトリ基準の相対パスになる。
    """
    argv = sys.argv[1:] if argv is None else argv
    base = argv[0] if argv else ""
    run(_Scan(sys.stdin), base)
    # 原本は `printf("time:%ld\n", …)` を出す。秒数は走るたびに変わるので
    # 移植では出さない（出力ファイルには影響しない）
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
