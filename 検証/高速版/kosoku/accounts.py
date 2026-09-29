# -*- coding: utf-8 -*-
"""勘定と流れ `Account` / `Transfer`（計画 §I）— ⑤④の台帳を「誰が誰に何を払うか」で読む
=============================================================================================
`検証/数式編/verify_cc.py` の恒等式をそのまま定義にする:

    収入計 = 保険料 ＋ 運用収入 ＋ 国庫負担 ＋ 支援入 ＋ 納付金 ＋ 妻積
    支出計 = 独自給付 ＋ 基礎年金拠出金 ＋ 事務費（福祉） ＋ 支援出
    収支差 = 収入計 − 支出計、積立金[y] = 積立金[y−1] ＋ 収支差[y]

勘定（yaml `accounts.*`）は既定で現行の 5 制度（厚年・国共済・地共済・私学・国年）＋ 基礎年金勘定
（pool）。流れ（yaml `transfers.*`）は基礎年金拠出金（5 制度 → pool、頭割り）、国庫負担（国 → 各制度、
拠出金 × 国庫負担割合 `kiso.kokko`）、支援金（厚年 → 共済 3 制度。一元化の経過措置）。

操作は全部データ:
    統合     `merge(ledger, [...], name)`   勘定を足す。統合する勘定の間の流れ（支援金）は消える
    税方式化 overlay `kiso_tax.yaml`（`kiso.kokko.after: 1.0`）  拠出金の国庫負担割合を 1 に → 各制度の
             拠出金と国庫負担が同額になり、基礎年金は全額が国（税）から pool へ。コードは変えない

言えるのは (1) 流れの from 側の和 = to 側の和、各勘定の収入計・支出計 = 部分和、積立金の漸化式
（`identities()`、相対 1e-9）、(2) 既定の yaml で⑤の `01shushi` がそのまま出る（`statement()` = ⑤の列）。
"""
from dataclasses import dataclass, field

import numpy as np

from .axis import YEARS

__all__ = ["Account", "Transfer", "Ledger", "ledger_of", "identities", "merge", "statement",
           "INFLOWS", "OUTFLOWS"]

INFLOWS = ("保険料", "運用収入", "国庫負担", "支援入", "納付金", "妻積")
OUTFLOWS = ("独自給付", "基礎年金拠出金", "事務費", "支援出")


@dataclass
class Account:
    name: str
    kind: str                          # employee / national / pool
    flows: dict = field(default_factory=dict)      # 流れの名前 → (YEARS.n,)
    fund: np.ndarray = None            # 年度末積立金
    shunyu: np.ndarray = None          # 台帳の収入計（検算用。無ければ流れの和）
    shishutu: np.ndarray = None
    members: tuple = ()                # 統合した元の勘定


@dataclass
class Transfer:
    name: str
    frm: tuple                         # 勘定名（"treasury" は国）
    to: tuple
    rule: str
    series: dict = field(default_factory=dict)     # 勘定名 → (YEARS.n,)。from 側は正、to 側は正


@dataclass
class Ledger:
    accounts: dict                     # 名前 → Account
    transfers: dict                    # 名前 → Transfer
    years: tuple                       # 恒等式を見る年度の範囲 (first, last)


def _z():
    return YEARS.zeros()


def ledger_of(pol, run5, run4=None):
    """⑤の run（`ShushiRun`）と④の run（`KisoRun`。無ければ国年と pool は作らない）から台帳を組む。
    勘定の名前と⑤の制度の対応は yaml `accounts.*.system`。"""
    from .stages.s5_emp_shushi.shushi import C
    from .stages.s5_emp_shushi.inputs import SYSTEMS
    A = pol.get("accounts")
    T = pol.get("transfers")
    Cc = run5.Cc
    i1, ie = YEARS.i(pol.get("shushi.years.kijun")) + 1, YEARS.i(run5.inp.ke)   # 基準年度の翌年度から（前は実績）
    acc = {}
    for name, spec in A.items():
        kind = spec["kind"]
        if kind == "employee":
            s = SYSTEMS.index(spec["system"])
            f = {"保険料": Cc[s, C.HOKENRYO].copy(), "運用収入": Cc[s, C.UNYO].copy(),
                 "国庫負担": Cc[s, C.KOKKO].copy(), "支援入": Cc[s, C.SHIEN_IN].copy(),
                 "納付金": Cc[s, C.NOFUKIN].copy(), "妻積": Cc[s, C.TUMATUMI].copy(),
                 "独自給付": Cc[s, C.DOKUJI].copy(), "基礎年金拠出金": Cc[s, C.KYOSHUTUKIN].copy(),
                 "事務費": Cc[s, C.JIMU].copy(), "支援出": Cc[s, C.SHIEN_OUT].copy(),
                 "国庫負担(基礎)": Cc[s, C.KOKKO_KISO].copy()}
            acc[name] = Account(name, kind, f, Cc[s, C.TUMITATE].copy(), Cc[s, C.SHUNYU].copy(),
                                Cc[s, C.SHISHUTU].copy())
        elif run4 is None:
            continue
        elif kind == "national":
            from .stages.s4_kiso_nenkin.output import kekka_series
            K = kekka_series(run4, "a")["収支見通し"]
            kokko = sum(K[k] for k in ("国庫（基礎年金）", "国庫（特別国庫）", "国庫（死亡一時金付加分）",
                                        "国庫（付加年金）", "国庫（旧法寡婦年金免除分）"))
            f = {"保険料": K["保険料収入（国年）"] + K["保険料収入（付加年金）"], "運用収入": K["運用収入"],
                 "国庫負担": kokko, "支援入": _z(), "納付金": _z(),
                 "妻積": K["妻積み"] + K["住宅融資債権"] + K["こども子育て特別会計から繰入"],
                 "独自給付": (K["死亡一時金納付分"] + K["死亡一時金付加分"] + K["新法寡婦年金"]
                              + K["旧法寡婦年金免除分以外"] + K["旧法寡婦年金免除分"] + K["付加年金"]),
                 "基礎年金拠出金": K["基礎年金拠出金"] + K["基礎年金拠出金（特別国庫）"],
                 "事務費": K["業務勘定への繰入"], "支援出": _z(), "国庫負担(基礎)": K["国庫（基礎年金）"]}
            acc[name] = Account(name, kind, f, K["年度末積立金"], K["収入合計"], K["支出合計"])
        elif kind == "pool":
            kyo = run4.kyo_a
            KY = run4.kyufu_a.k.K                                      # (NS, Y, NA, 新旧, 種類, 拠出/交付, 2)
            from .stages.s4_kiso_nenkin.kyufu import KYO
            kyufu = KY[:, :, :, :, :, KYO, :].sum(axis=(0, 2, 3, 4, 5))   # 拠出金の対象になる基礎年金給付費
            f = {"基礎年金拠出金": kyo.kyoshutukin[:, :, 0, 0].sum(axis=0), "基礎年金給付": kyufu}
            acc[name] = Account(name, kind, f, None, None, None)
    tr = {}
    for name, spec in T.items():
        frm, to = tuple(spec["from"]), tuple(spec["to"])
        t = Transfer(name, frm, to, spec["rule"])
        if spec["rule"] == "atamawari" and run4 is not None:            # 拠出金: 各制度 → pool
            kyo = run4.kyo_a.kyoshutukin[:, :, 0, 0]                    # (NS, Y) 国年, 厚年, 国共, 地共, 私学
            order = ("kokunen", "kounen", "kokkyo", "chikyo", "shigaku")
            for k, nm in enumerate(order):
                if nm in frm and nm in acc:
                    t.series[nm] = kyo[k].copy()
            t.series[to[0]] = kyo.sum(axis=0)
        elif spec["rule"] == "share_of_kyoshutsu":                     # 国庫負担: 国 → 各制度（拠出金 × 割合）
            for nm in to:
                if nm in acc:
                    t.series[nm] = acc[nm].flows["国庫負担(基礎)"].copy()
            t.series["treasury"] = sum(t.series[nm] for nm in to if nm in acc)
        elif spec["rule"] == "shien":                                   # 支援金: 厚年 → 共済
            for nm in frm:
                if nm in acc:
                    t.series[nm] = acc[nm].flows["支援出"].copy()
            for nm in to:
                if nm in acc:
                    t.series[nm] = acc[nm].flows["支援入"].copy()
        tr[name] = t
    return Ledger(acc, tr, (YEARS.label(i1), YEARS.label(ie)))


def statement(a):
    """勘定の 収入計・支出計・収支差・積立金 を流れから作る（`01shushi` の列の定義）。"""
    f = a.flows
    if a.kind == "pool":
        inn, out = f["基礎年金拠出金"], f["基礎年金給付"]
        return {"収入計": inn, "支出計": out, "収支差": inn - out}
    inn = sum(f[k] for k in INFLOWS)
    out = sum(f[k] for k in OUTFLOWS)
    st = {"収入計": inn, "支出計": out, "収支差": inn - out}
    if a.fund is not None:
        st["積立金"] = a.fund
    return st


def _rel(a, b):
    den = np.maximum(np.abs(b), 1.)
    return float(np.max(np.abs(a - b) / den))


def identities(L, rtol=1e-9):
    """恒等式を全部見る → [(名前, 最大相対差, OK)]。"""
    i1, ie = YEARS.i(L.years[0]), YEARS.i(L.years[1])
    sl = slice(i1, ie + 1)
    out = []
    for a in L.accounts.values():
        st = statement(a)
        if a.shunyu is not None:
            out.append(("%s 収入計 = 部分和" % a.name, _rel(st["収入計"][sl], a.shunyu[sl])))
            out.append(("%s 支出計 = 部分和" % a.name, _rel(st["支出計"][sl], a.shishutu[sl])))
        if a.fund is not None:
            rec = a.fund[i1 - 1:ie] + st["収支差"][sl]
            out.append(("%s 積立金の漸化式" % a.name, _rel(rec, a.fund[sl])))
        if a.kind == "pool":
            out.append(("%s 拠出金 = 基礎年金給付（頭割り）" % a.name, _rel(st["収入計"][sl], st["支出計"][sl])))
    for t in L.transfers.values():
        if not t.series:
            continue
        frm = sum(t.series[n] for n in t.frm if n in t.series) if any(n in t.series for n in t.frm) else None
        to = sum(t.series[n] for n in t.to if n in t.series) if any(n in t.series for n in t.to) else None
        if frm is not None and to is not None:
            out.append(("流れ %s: from の和 = to の和" % t.name, _rel(frm[sl], to[sl])))
    return [(n, d, d <= rtol) for n, d in out]


def merge(L, names, new_name):
    """勘定を統合する（流れは足す。統合する勘定の間だけで閉じる流れ＝支援金は消える）。"""
    names = tuple(names)
    members = [L.accounts[n] for n in names]
    kinds = {a.kind for a in members}
    if kinds != {"employee"}:
        raise ValueError("統合できるのは被用者年金の勘定だけ: %s" % kinds)
    f = {k: sum(a.flows[k] for a in members) for k in members[0].flows}
    for t in L.transfers.values():
        if t.rule == "shien" and set(t.frm) <= set(names) and set(t.to) <= set(names):
            f["支援入"] = f["支援入"] - sum(t.series.get(n, 0.) for n in t.to)
            f["支援出"] = f["支援出"] - sum(t.series.get(n, 0.) for n in t.frm)
    fund = sum(a.fund for a in members)
    shunyu = sum(a.shunyu for a in members) - (sum(a.flows["支援入"] for a in members) - f["支援入"])
    shishutu = sum(a.shishutu for a in members) - (sum(a.flows["支援出"] for a in members) - f["支援出"])
    acc = {n: a for n, a in L.accounts.items() if n not in names}
    acc[new_name] = Account(new_name, "employee", f, fund, shunyu, shishutu, names)
    tr = {}
    for t in L.transfers.values():
        s = {}
        for n, v in t.series.items():
            key = new_name if n in names else n
            s[key] = s.get(key, 0.) + v
        frm = tuple(dict.fromkeys(new_name if n in names else n for n in t.frm))
        to = tuple(dict.fromkeys(new_name if n in names else n for n in t.to))
        if t.rule == "shien" and frm == (new_name,) and to == (new_name,):
            continue                                                    # 内部の流れは消える
        tr[t.name] = Transfer(t.name, frm, to, t.rule, s)
    return Ledger(acc, tr, L.years)
