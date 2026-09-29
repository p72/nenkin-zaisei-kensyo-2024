#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""移植版①〜⑤の公開関数を ast で数え上げ、対応表の骨格を吐く
===============================================================
高速版は「完全に再構築のサブセット」なので、対応表は仕様書の節ではなく
**移植版の関数一覧**から作る（`計画.md`「大前提」2）。

数え方（この定義を変えたら台帳も作り直す）
------------------------------------------
- 対象: `検証/移植/{hihokensha,emp_kyufu,nat,kiso_nenkin,emp_shushi}/*.py`
  （`__init__.py`・`_` で始まるファイルは除く。`clib/` と `bunpu/` は対象外）
- 数えるもの: モジュール直下の `def`、モジュール直下の `class` の中の `def`、
  モジュール直下の関数の**直下**にある `def`（1段だけの入れ子。`outer>inner`
  と書く）。名前が `_` で始まるものは除く（`__init__` も除く）
- 数えないもの: 2段以上の入れ子、`if __name__` の中の `def`、`lambda`、
  `async def`（無い）

この数え方で ①55 ②79 ③76 ④33 ⑤76 = 319 になり、`計画.md` の数と一致する。
入れ子の7本（`fout.py:_vec>pn` など）は親の一部として整理する。

使い方
------
    python3 検証/高速版/tools/ledger_inventory.py            # 表を標準出力へ
    python3 検証/高速版/tools/ledger_inventory.py --merge 対応表.md
        既存の対応表の「仕様／高速版／区分／理由」列を港の関数名で引き継いで
        新しい骨格に流し込む（関数が増減したときに手入力を失わないため）

出力の列: `| # | 系統 | 港の関数 | 仕様 | 高速版 | 区分 | 理由 |`
"""
import argparse
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = os.path.normpath(os.path.join(HERE, "..", "..", "移植"))

SYSTEMS = (
    ("①", "hihokensha"),
    ("②", "emp_kyufu"),
    ("③", "nat"),
    ("④", "kiso_nenkin"),
    ("⑤", "emp_shushi"),
)

ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.*?)\s*\|"
                 r"\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$")


def public_functions(path):
    """1ファイルの公開関数名（`Class.method` を含む）を宣言順で返す。"""
    with open(path, encoding="utf-8") as fp:
        tree = ast.parse(fp.read(), filename=path)
    out = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if not node.name.startswith("_"):
                out.append(node.name)
            for m in node.body:
                if isinstance(m, ast.FunctionDef) and not m.name.startswith("_"):
                    out.append("%s>%s" % (node.name, m.name))
        elif isinstance(node, ast.ClassDef):
            for m in node.body:
                if isinstance(m, ast.FunctionDef) and not m.name.startswith("_"):
                    out.append("%s.%s" % (node.name, m.name))
    return out


def inventory(port=PORT):
    """[(系統, 'dir/file.py:func'), …] を系統・ファイル・宣言順で返す。"""
    rows = []
    for mark, d in SYSTEMS:
        base = os.path.join(port, d)
        for f in sorted(os.listdir(base)):
            if not f.endswith(".py") or f.startswith("_"):
                continue
            for fn in public_functions(os.path.join(base, f)):
                rows.append((mark, "%s/%s:%s" % (d, f, fn)))
    return rows


def read_existing(path):
    """既存の対応表から 港の関数 → (仕様, 高速版, 区分, 理由) を拾う。"""
    got = {}
    if not path or not os.path.isfile(path):
        return got
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            m = ROW.match(line.rstrip("\n"))
            if m and m.group(3).strip("`"):
                got[m.group(3).strip("`")] = m.groups()[3:]
    return got


def render(rows, existing):
    counts = {}
    for mark, _ in rows:
        counts[mark] = counts.get(mark, 0) + 1
    out = []
    out.append("# 対応表 — 移植版の公開関数と高速版の対応")
    out.append("")
    out.append("`tools/ledger_inventory.py` が骨格を生成する。**港の関数の列は手で"
               "編集しない**（再生成で消える）。仕様／高速版／区分／理由の4列だけ"
               "手で埋める。")
    out.append("")
    out.append("数え方: モジュール直下の `def` とクラス直下の `def`、`_` 始まりを除く"
               "（`tools/ledger_inventory.py` の先頭に定義）。")
    out.append("")
    out.append("| 系統 | 関数数 |")
    out.append("|---|---:|")
    for mark, d in SYSTEMS:
        out.append("| %s `%s` | %d |" % (mark, d, counts.get(mark, 0)))
    out.append("| **計** | **%d** |" % len(rows))
    out.append("")
    out.append("区分の語彙: **実装**（高速版の関数名を書く。N:1 可）／"
               "**意図して省略**（理由は `書式 / 入出力 / 癖再現 / ⑥ / デバッグ印字 / 未使用`）／"
               "**該当なし**（C 言語由来）／**新規**（高速版だけにある。港の関数は `—`）。"
               "空欄は未整理。")
    out.append("")
    out.append("| # | 系統 | 港の関数 | 仕様 | 高速版 | 区分 | 理由 |")
    out.append("|---|---|---|---|---|---|---|")
    for i, (mark, fn) in enumerate(rows, 1):
        spec, fast, kind, why = existing.get(fn, ("", "", "", ""))
        out.append("| %d | %s | `%s` | %s | %s | %s | %s |"
                   % (i, mark, fn, spec, fast, kind, why))
    # 高速版だけにある行（区分 新規）は港の関数が `—` なので引き継ぐ
    extra = [(k, v) for k, v in existing.items() if k == "—"]
    n = len(rows)
    for k, v in extra:
        n += 1
        out.append("| %d | — | — | %s | %s | %s | %s |" % ((n,) + tuple(v)))
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--merge", metavar="対応表.md",
                    help="既存の対応表の手入力列を引き継ぐ")
    ap.add_argument("--port", default=PORT, help="移植版のディレクトリ")
    a = ap.parse_args(argv)
    rows = inventory(a.port)
    sys.stdout.write(render(rows, read_existing(a.merge)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
