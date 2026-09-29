# -*- coding: utf-8 -*-
"""オプション試算のレバー（仕様 §11.1、`検証/実行/run_pipeline.sh` の 7 つの環境変数）
========================================================================================
値は policy の `options.*`（`base_2024.yaml` の既定 = 通常試算）。`policy/options/*.yaml` の
overlay で 1 つずつ変える（`load_policy("kozax")` など。複数可）。

    kakudai  0〜5  被用者保険の適用拡大          ① MODE / ② flg_part / ③ Part / ⑤ Flg_Part
    sigo     0/1   基礎年金の拠出期間 45 年化    ① MODE45 / ② flg_sigo / ⑤ Flg_Sigo
    kozax    0/1   65 歳以上の在職老齢年金の撤廃 ② flg_kozax（③④は据え置く: `freeze_kiso`）
    houjou   0〜3  標準報酬月額の上限の見直し    ② houjou / ⑤ Flg_Houjou（同上）
    tougou   0/1   調整期間の一致                ④ TOUGOU / ⑤ Touitu（④→⑤→④）
    dmacro   0/1   名目下限措置の撤廃            ④ DMACRO / ⑤ Flg_Dmakuro
    carry    0/1   キャリーオーバー（1 = 現行）  ④ CARRY / ⑤ Flg_Kmakuro（= 1 − carry）

`freeze_kiso`: 高在老の撤廃と標準報酬上限は報酬比例にしか効かないので、③④は通常試算のまま据え置いて
②⑤だけ流し直す（仕様 §11.2、`run_pipeline.sh` の `STEPS=25`）。
"""
from dataclasses import dataclass

__all__ = ["Options", "options_of", "NAMES"]

NAMES = ("kakudai", "sigo", "kozax", "houjou", "tougou", "dmacro", "carry")
_RANGE = {"kakudai": range(0, 6), "sigo": (0, 1), "kozax": (0, 1), "houjou": range(0, 4),
          "tougou": (0, 1), "dmacro": (0, 1), "carry": (0, 1)}


@dataclass(frozen=True)
class Options:
    kakudai: int = 0
    sigo: int = 0
    kozax: int = 0
    houjou: int = 0
    tougou: int = 0
    dmacro: int = 0
    carry: int = 1

    @property
    def freeze_kiso(self):
        """③④を通常試算のまま据え置くレバーだけが立っているか（§11.2）。"""
        return (self.kozax or self.houjou) and not (self.kakudai or self.sigo or self.tougou
                                                    or self.dmacro or not self.carry)

    @property
    def tag(self):
        """`kozax` `houjou3` `nocarry` のような短い名前（通常試算は `base`）。"""
        parts = []
        if self.kakudai:
            parts.append("kakudai%d" % self.kakudai)
        if self.sigo:
            parts.append("sigo")
        if self.kozax:
            parts.append("kozax")
        if self.houjou:
            parts.append("houjou%d" % self.houjou)
        if self.tougou:
            parts.append("tougou")
        if self.dmacro:
            parts.append("dmacro")
        if not self.carry:
            parts.append("nocarry")
        return "+".join(parts) or "base"


def options_of(pol):
    """policy の `options.*` → `Options`。範囲外は止める。"""
    node = pol.get("options", {})
    kw = {}
    for n in NAMES:
        v = int(node.get(n, Options.__dataclass_fields__[n].default))
        if v not in _RANGE[n]:
            raise ValueError("options.%s = %r は範囲外" % (n, v))
        kw[n] = v
    return Options(**kw)
