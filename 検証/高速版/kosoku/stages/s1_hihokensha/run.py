# -*- coding: utf-8 -*-
"""①被保険者推計の通し（移植版 `main.c`）
=========================================
    read_inputs  設定と 17 本の CSV（`inputs`）
    run          setjinko → simlroud → simlkyos → simlkou → simlichisan → simlpart → cutritu
                 → 58 分類の表 → `Waku`

港の `zero`（配列の 0 埋め）と各段の `printf` は無い。出力は `output.to_port_csv` で港の配置に書ける。

港: hihokensha/main.py:run, main
仕様: §2、§12.4
"""
from dataclasses import dataclass

import numpy as np

from ...contracts import Waku, Provenance, policy_hash, git_rev
from .inputs import read_inputs, HihoInputs, Settings, Hiho
from .jinko import setjinko
from .roudou import simlroud
from .kounen import simlkyos, simlkou
from .ichisan import simlichisan
from .part import simlpart
from .cutritu import cutritu
from .output import class_table, to_waku

__all__ = ["HihoRun", "read_inputs", "run"]


@dataclass
class HihoRun:
    out: Waku
    S: Settings
    H: Hiho
    cut: np.ndarray              # 調整率（cy の軸。小数 6 桁）
    cut2: np.ndarray             # 1 / 率 − 1（小数 4 桁。waku-m の値）


def run(inp, case, upstream=()):
    """1 ケースを通す。港: hihokensha/main.py:run"""
    S, H = inp.S, inp.H
    setjinko(S, H)
    simlroud(S, H)
    simlkyos(S, H)
    simlkou(S, H)
    simlichisan(S, H)
    simlpart(S, H)
    cut, cut2 = cutritu(S, H)
    T = class_table(S, H)
    prov = Provenance(case=str(case), stage="s1", source="fast", policy=policy_hash(inp.pol.data),
                      rev=git_rev(), upstream=tuple(upstream),
                      note="jin=%d qx=%d nc=%d roudr=%d mode=%d mode45=%d"
                           % (S.jin, S.qx, S.nc, S.roudr, S.mode, S.mode45))
    return HihoRun(to_waku(S, T, cut2, prov), S, H, cut, cut2)
