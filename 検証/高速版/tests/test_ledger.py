# -*- coding: utf-8 -*-
"""対応表の約束
==============
- `対応表.md` の港の関数の列は `tools/ledger_inventory.py` の出力と一致する
  （関数が増減したら `--merge` で作り直す）
- 区分は語彙内。理由の語彙も
- 高速版の公開関数（またはそのモジュール）が `港: X` を引くなら、X は台帳の行にある
- `stages/` と `kernels/recur.py` の公開関数は `港:` と `仕様:` を必ず持つ
"""
import ast
import os
import re
import sys

import pytest

from conftest import FAST

sys.path.insert(0, os.path.join(FAST, "tools"))
import ledger_inventory as LI                       # noqa: E402

LEDGER = os.path.join(FAST, "対応表.md")
KINDS = {"実装", "意図して省略", "該当なし", "新規", ""}
WHY_OMIT = {"書式", "入出力", "癖再現", "⑥", "デバッグ印字", "未使用"}
# `港: dir/file.py:func` または `港: dir/file.py:func1, func2, …`
PORT_REF = re.compile(r"港:\s*([A-Za-z0-9_/]+\.py):([A-Za-z0-9_.>]+(?:\s*,\s*[A-Za-z0-9_.>]+)*)")
SPEC_REF = re.compile(r"仕様:\s*(§[^\s]+)")


def _rows():
    rows = []
    for line in open(LEDGER, encoding="utf-8"):
        m = LI.ROW.match(line.rstrip("\n"))
        if m:
            rows.append(m.groups())
    return rows


def test_港の関数の列が生成結果と一致():
    inv = [fn for _, fn in LI.inventory()]
    got = [r[2].strip("`") for r in _rows() if r[2].strip("`") != "—"]
    assert got == inv, "対応表.md を tools/ledger_inventory.py --merge 対応表.md で作り直す"


def test_区分と理由の語彙():
    bad = []
    for r in _rows():
        n, sys_, fn, spec, fast, kind, why = r
        if kind not in KINDS:
            bad.append("%s: 区分 %r" % (fn, kind))
        if kind == "意図して省略":
            head = why.split(":")[0].split("：")[0].strip()
            if head not in WHY_OMIT:
                bad.append("%s: 省略の理由 %r は語彙外" % (fn, why))
        if kind == "実装" and not fast:
            bad.append("%s: 実装なら高速版の関数名を書く" % fn)
    assert not bad, "\n".join(bad)


def _public_defs():
    pkg = os.path.join(FAST, "kosoku")
    for root, _, files in os.walk(pkg):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            tree = ast.parse(open(path, encoding="utf-8").read())
            mod_doc = ast.get_docstring(tree) or ""
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                    yield os.path.relpath(path, pkg), node.name, (ast.get_docstring(node) or ""), mod_doc


def test_港の引用先が台帳にある():
    inv = set(fn for _, fn in LI.inventory())
    bad = []
    for rel, name, doc, mod_doc in _public_defs():
        for text in (doc, mod_doc):
            for base, fns in PORT_REF.findall(text):
                for fn in fns.split(","):
                    key = "%s:%s" % (base, fn.strip())
                    if key not in inv:
                        bad.append("%s:%s 港: %s は台帳に無い" % (rel, name, key))
    assert not bad, "\n".join(bad)


def test_段階とカーネルの公開関数は港と仕様を引く():
    """関数の docstring に無ければ、そのモジュールの docstring の引用で足りる
    （読み手のように1モジュールが1〜2本の港の関数に対応するとき）。"""
    bad = []
    for rel, name, doc, mod_doc in _public_defs():
        if rel.startswith("stages" + os.sep) or rel == os.path.join("kernels", "recur.py"):
            text = doc if (PORT_REF.search(doc) and SPEC_REF.search(doc)) else mod_doc
            if not PORT_REF.search(text) or not SPEC_REF.search(text):
                bad.append("%s:%s" % (rel, name))
    assert not bad, "港: と 仕様: を docstring に:\n" + "\n".join(bad)
