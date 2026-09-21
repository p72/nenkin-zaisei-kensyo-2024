# -*- coding: utf-8 -*-
"""
`str_op` の2つの実装が、どの型でもビット一致すること
======================================================
`nat/str_op.py` は速度のために**実装を2本持っている**。

- **平べったい版** — 構造体を「float64 が n 個」として view し、
  1回のベクトル演算で済ませる。1回 2.1〜2.4us
- **欄ごと版** — 原本のとおり欄を1つずつ代入する。小さい型では
  こちらが速い（view と ufunc の呼び出しに 2.1us の床があるため）

`_flat(dt)` が型のスロット数を見て選び、境目は `FLAT_MIN`（= 5）。

原本Cとの突き合わせは `test_nat_stage.py` の
`test_str_opの8つの型の演算が原本と一致` が44通りやっているが、それは
**決めた普通の値**での話で、しかも本番で通らない側の経路は試していない。
ここで埋めるのはその2つ。

1. **`FLAT_MIN` を動かして両方の経路を全型で通す。** 本番では
   HIHOKENSHA の欄ごと版も GONEN の平べったい版も走らないので、
   このテストが無いと片方が死んだコードになる
2. **極端な値を当てる。** `±0` `±Inf` `NaN` `1e308` `1e-308` と極小値。
   欄ごと版は NumPy のスカラー演算、平べったい版は ufunc を通るので、
   特殊値の扱いが違わないことを押さえておく

なぜビット一致が言えるのか
--------------------------
`add` `scalar` `multiply` `adjustbenefit` `average_by_ninzu` は
**各欄の出力が double 1〜2個の1回の演算**で、総和を取っていない
（縮約ではない）。`nendokan` `nendokan_64` `scalar_2` も、重みを
掛ける順・足す順を原本のまま保っている。要素ごとの演算をまとめても
各要素にかかる演算の順序は変わらないので、書き方を変えても結果は
1ビットも動かない（`検証/移植/README.md`「ベクトル化はビット一致を
壊さない」）。

`_check_covered()` が支える前提
-------------------------------
平べったい版が正しいのは「`ninzu` ＋ `_FIELDS[dt]` が**全スロットを
覆っている**」からで、覆えていない欄があると欄ごと版はその欄を 0 の
まま残すため結果が変わる。`str_op` は読み込み時に `_check_covered()`
でこれを確かめて落ちる。ここでもその検査が生きていることを試す。
"""
import itertools
import zlib

import numpy as np
import pytest

from portpath import select  # noqa: E402

SYSTEMS = ("clib", "nat")
select(*SYSTEMS)

import str_op as S                                      # noqa: E402
from setconst import SUM, TOKUTEI_NENDO, TOKUTEI_TUKI   # noqa: E402

DTYPES = {n: v for n, v in vars(S).items()
          if isinstance(v, np.dtype) and v.names}


# ---- `scalar_2` と `average_by_ninzu` の参照実装 --------------------
#
# この2つは `hihokensha`（21スロット）だけに定義があるので、本番では
# 必ず平べったい経路を通る。欄ごと版を `str_op` に残しても production
# では動かない死んだコードになるだけなので、**最適化する前の実装を
# ここに凍結して置く**。これは原本Cと出力がバイト一致していた版で、
# `test_nat_stage.py` が原本と突き合わせている。
#
# ほかの6関数は型によって本番でも両方の経路が走るので、`str_op` の中に
# 両方置いてある（`FLAT_MIN` で切り替わる）。


def _ref_scalar_2(s, x, nendo):
    """最適化前の `scalar_2`（欄ごとに代入する版）。"""
    out = np.zeros((), dtype=S.HIHOKENSHA)
    if nendo <= TOKUTEI_NENDO:
        kokko1, kokko2 = 1, 2
    else:
        kokko1, kokko2 = 2, 1
    out["ninzu"] = s * x["ninzu"]
    out["kikan"] = s * x["kikan"]
    out["noufu"] = s * x["noufu"]
    om, xm = out["menjo"], x["menjo"]
    if nendo == TOKUTEI_NENDO:
        om[:, kokko1] = s * xm[:, kokko1] * (TOKUTEI_TUKI - 4) / 12.
        om[:, kokko2] = s * xm[:, kokko2] * (16 - TOKUTEI_TUKI) / 12.
    else:
        om[:, kokko1] = s * xm[:, kokko1]
        om[:, kokko2] = 0.
    om[:, SUM] = om[:, kokko1] + om[:, kokko2]
    out["gakusei"] = s * x["gakusei"]
    out["wakamono"] = s * x["wakamono"]
    out["fuka"] = s * x["fuka"]
    return out


def _ref_average_by_ninzu(x):
    """最適化前の `average_by_ninzu`（`ninzu > 0.` を欄ごとに見る版）。"""
    out = np.zeros((), dtype=S.HIHOKENSHA)
    n = x["ninzu"]
    out["ninzu"] = n
    pos = (n > 0.)
    for f in S._FIELDS[S.HIHOKENSHA]:
        out[f] = (x[f] / n) if pos else 0.
    return out

# 当てる値。特殊値は「欄ごと版はスカラー演算・平べったい版は ufunc」の
# 差が出るとすればここに出る
SPECIAL = (0.0, -0.0, 1.0, -1.0, 1e308, 1e-308, np.inf, -np.inf, np.nan,
           0.1, 1. / 3, 12345.6789, -98765.4321)
SCALARS = (0.0, 1.0, -1.0, 0.5, 1. / 3, 1e10, 1e-10, np.nan, np.inf)
KAITEI = (1.0, 0.0, 0.997, 1.0404, -0.5, 1e6)
MODES = ("rand", "zero", "special", "tiny")


def _fill(dt, mode, seed):
    """`dt` の1個を作って、決めた流儀で値を埋める。"""
    n = dt.itemsize // 8
    a = np.zeros((), dtype=dt)
    v = a.reshape(1).view(np.float64)
    rng = np.random.default_rng(seed)
    if mode == "rand":
        v[:] = rng.standard_normal(n) * 1e5
    elif mode == "zero":
        v[:] = 0.
    elif mode == "special":
        v[:] = [SPECIAL[(i * 7 + 3) % len(SPECIAL)] for i in range(n)]
    elif mode == "tiny":
        v[:] = rng.standard_normal(n) * 1e-300
    return a


def _crc(x):
    """NaN が入っていても比べられるようにバイト列で見る。"""
    return zlib.crc32(np.ascontiguousarray(x).tobytes())


class _Flat(object):
    """`FLAT_MIN` を差し替えて、選ばれる経路を強制する。

    `_flat()` の答えを控えている `_FLAT` も空にする。
    """

    def __init__(self, flat_min):
        self.flat_min = flat_min

    def __enter__(self):
        self.saved = S.FLAT_MIN
        S.FLAT_MIN = self.flat_min
        S._FLAT.clear()
        S._NDK_W1.clear()
        return self

    def __exit__(self, *a):
        S.FLAT_MIN = self.saved
        S._FLAT.clear()
        S._NDK_W1.clear()
        return False


# 0 なら全型が平べったい版、`10**9` なら全型が欄ごと版
BOTH = (0, 10 ** 9)


def _both(fn, *args):
    """両方の経路で `fn(*args)` を呼び、CRC32 を返す。"""
    out = []
    for fm in BOTH:
        with _Flat(fm):
            out.append(_crc(fn(*args)))
    return out


# `1e308` や `±Inf` をわざと当てるので overflow と invalid は必ず出る。
# **出ること自体は異常ではなく**、両方の経路で同じ結果になるかだけを見る。
# NumPy 側（`np.errstate`）と pytest 側の両方で黙らせておく
pytestmark = pytest.mark.filterwarnings("ignore::RuntimeWarning")


@pytest.fixture(autouse=True)
def _quiet_numpy():
    with np.errstate(all="ignore"):
        yield


@pytest.mark.parametrize("name", sorted(DTYPES))
def test_addとscalarが両方の経路でビット一致(name):
    """全8型の `add` `scalar`。値の流儀を総当たりする。"""
    dt = DTYPES[name]
    n = 0
    for i, (m1, m2) in enumerate(itertools.product(MODES, MODES)):
        a = _fill(dt, m1, 100 + i)
        b = _fill(dt, m2, 200 + i)
        flat, field = _both(S.add, a, b)
        assert flat == field, "%s の add が経路で違う（%s, %s）" % (
            name, m1, m2)
        n += 1
        for s in SCALARS:
            flat, field = _both(S.scalar, s, a)
            assert flat == field, "%s の scalar が経路で違う（%s, %r）" % (
                name, m1, s)
            n += 1
    assert n >= 16, "空振りしている（%d 通りしか見ていない）" % n


@pytest.mark.parametrize("name", sorted(DTYPES))
def test_型ごとに定義のある演算が両方の経路でビット一致(name):
    """`multiply` `nendokan` `nendokan_64` `adjustbenefit`
    `average_by_ninzu`。原本に定義のある型だけ当てる
    （`str_op` の冒頭の表のとおり）。"""
    dt = DTYPES[name]
    checked = 0
    for i, m in enumerate(MODES):
        a = _fill(dt, m, 300 + i)
        b = _fill(dt, m, 400 + i)
        c = _fill(dt, "rand", 500 + i)

        if dt in (S.ROREI, S.ROREI_KYU, S.SHOGAI, S.IZOKU, S.KAFU):
            flat, field = _both(S.multiply, a, b)
            assert flat == field, "%s の multiply が経路で違う" % name
            checked += 1

        if dt is not S.HIHOKENSHA:
            k2 = dt in S._KAITEI2
            for kr in KAITEI:
                args = (a, b, kr, (kr * 1.01) if k2 else None)
                flat, field = _both(S.nendokan, *args)
                assert flat == field, \
                    "%s の nendokan が経路で違う（改定率 %r）" % (name, kr)
                checked += 1

        if dt not in (S.HIHOKENSHA, S.KAFU):
            for kr in KAITEI:
                flat, field = _both(S.nendokan_64, a, b, c, kr)
                assert flat == field, \
                    "%s の nendokan_64 が経路で違う（改定率 %r）" % (name, kr)
                checked += 1

        if dt not in (S.HIHOKENSHA, S.ICHIJIKIN):
            for s in SCALARS:
                flat, field = _both(S.adjustbenefit, s, a)
                assert flat == field, \
                    "%s の adjustbenefit が経路で違う（%r）" % (name, s)
                checked += 1

    # `average_by_ninzu` は hihokensha だけなので経路は1つ。
    # 最適化前の実装（参照実装）と突き合わせる
    if dt is S.HIHOKENSHA:
        for i, m in enumerate(MODES):
            a = _fill(dt, m, 600 + i)
            assert _crc(S.average_by_ninzu(a)) \
                == _crc(_ref_average_by_ninzu(a)), \
                "average_by_ninzu が参照実装と違う（%s）" % m
            checked += 1
    else:
        assert checked > 0, "%s で1通りも見ていない" % name


def test_scalar_2が参照実装とビット一致():
    """`hihokensha` だけ。**特定年度（2009年度）の前・当年・翌年**を
    必ず含める。`menjo` の列が入れ替わる枝と按分する枝の両方を通す。

    `scalar_2` は書き換えがいちばん危ない。`s * x * c / 12.` を
    `x * (s * c / 12.)` に畳むと丸めが変わるので、平べったい版は
    いったん全スロットに `s` を掛けてから `menjo` の列だけを
    原本と同じ順で加工している。ここで固定するのはその等価性。
    """
    dt = S.HIHOKENSHA
    nendos = (TOKUTEI_NENDO - 1, TOKUTEI_NENDO, TOKUTEI_NENDO + 1,
              2020, 2125)
    n = 0
    for i, m in enumerate(MODES):
        a = _fill(dt, m, 700 + i)
        for nd in nendos:
            for s in SCALARS:
                assert _crc(S.scalar_2(s, a, nd)) \
                    == _crc(_ref_scalar_2(s, a, nd)), \
                    "scalar_2 が参照実装と違う（%s, %d年度, %r）" % (m, nd, s)
                n += 1
    assert n == len(MODES) * len(nendos) * len(SCALARS)


def test_平べったい版が全スロットを覆っている():
    """`_check_covered()` が生きていること。

    `ninzu` ＋ `_FIELDS[dt]` が全スロットを覆っていないと、平べったい版は
    欄ごと版と違う結果を出す。欄を足したときに黙って壊れないよう、
    `str_op` は読み込み時にこれを確かめている。ここでは**わざと欄を
    隠して落ちること**を試す。
    """
    S._check_covered()          # 今の定義では通る

    saved = S._FIELDS[S.ROREI]
    try:
        S._FIELDS[S.ROREI] = saved[:-1]     # `fuka` を隠す
        with pytest.raises(AssertionError) as e:
            S._check_covered()
        assert "覆えていない" in str(e.value)
    finally:
        S._FIELDS[S.ROREI] = saved
    S._check_covered()          # 戻したら通る


def test_FLAT_MINの境目が実際の型の寸法と合っている():
    """`FLAT_MIN` が意味のある位置にあること。

    実測での境目は5スロット。全型のスロット数は
    GONEN 2 / IZOKU 3 / ICHIJIKIN 3 / SHOGAI 5 / ROREI_KYU 7 /
    KAFU 17 / ROREI 19 / HIHOKENSHA 21 なので、`FLAT_MIN` = 5 だと
    **両方の経路が実際に使われる**（片方が死んだコードにならない）。
    """
    sizes = {n: dt.itemsize // 8 for n, dt in DTYPES.items()}
    assert sizes == {"GONEN": 2, "IZOKU": 3, "ICHIJIKIN": 3, "SHOGAI": 5,
                     "ROREI_KYU": 7, "KAFU": 17, "ROREI": 19,
                     "HIHOKENSHA": 21}, sizes

    flat = {n for n, k in sizes.items() if k >= S.FLAT_MIN}
    field = set(sizes) - flat
    assert flat and field, \
        "FLAT_MIN=%d だと片方の経路が使われない" % S.FLAT_MIN
    assert field == {"GONEN", "IZOKU", "ICHIJIKIN"}, field

    # `_flat()` が判定と dtype 取得を兼ねている
    for n, dt in DTYPES.items():
        f = S._flat(dt)
        if n in field:
            assert f is None, "%s は欄ごと版のはず" % n
        else:
            assert f is not None and f.shape == (sizes[n],), n


@pytest.mark.parametrize("name", sorted(DTYPES))
def test_軸まとめ版が1個ずつ呼ぶのとビット一致(name):
    """`scalar_arr` `adjustbenefit_arr` `multiply_arr` `add_arr`。

    軸をまとめてよいのは「出力のスロットごとに当たる演算の列が
    変わらない」ときだけ。ここで試すのはその前提が成り立つ形
    （入力と出力が別の配列で、要素が1対1に対応する場合）で、
    **1個ずつ呼んだ結果と1ビットも変わらない**こと。

    放送も試す。`siml` は年齢ごとに違う係数を
    `s[:, None, None]` の形で渡すので、その形を通す。
    """
    dt = DTYPES[name]
    shape = (7, 5)                      # (年齢, 受給年齢) に見立てる
    n = dt.itemsize // 8

    rng = np.random.default_rng(900 + len(name))
    a = np.zeros(shape, dtype=dt)
    b = np.zeros(shape, dtype=dt)
    a.reshape(-1).view(np.float64)[:] = \
        rng.standard_normal(shape[0] * shape[1] * n) * 1e5
    b.reshape(-1).view(np.float64)[:] = \
        rng.standard_normal(shape[0] * shape[1] * n) * 1e5
    # 特殊値も混ぜる
    a.reshape(-1).view(np.float64)[::5] = np.inf
    a.reshape(-1).view(np.float64)[1::7] = -0.0
    b.reshape(-1).view(np.float64)[2::11] = np.nan

    # 行（年齢）ごとに違う係数。放送の形は `[:, None, None]`
    s_row = rng.standard_normal(shape[0])
    s_b = s_row[:, None, None]

    def _one(fn, *args):
        """1個ずつ呼んで同じ形に詰める。"""
        out = np.zeros(shape, dtype=dt)
        for i in range(shape[0]):
            for k in range(shape[1]):
                out[i, k] = fn(i, k)
        return out

    # scalar_arr
    got = S.scalar_arr(s_b, a, np.empty(shape, dtype=dt))
    want = _one(lambda i, k: S.scalar(s_row[i], a[i, k]))
    assert _crc(got) == _crc(want), "%s の scalar_arr が違う" % name

    # add_arr
    got = S.add_arr(a, b, np.empty(shape, dtype=dt))
    want = _one(lambda i, k: S.add(a[i, k], b[i, k]))
    assert _crc(got) == _crc(want), "%s の add_arr が違う" % name

    # multiply_arr（原本に定義のある型だけ）
    if dt in (S.ROREI, S.ROREI_KYU, S.SHOGAI, S.IZOKU, S.KAFU):
        got = S.multiply_arr(a, b, np.empty(shape, dtype=dt))
        want = _one(lambda i, k: S.multiply(a[i, k], b[i, k]))
        assert _crc(got) == _crc(want), "%s の multiply_arr が違う" % name
    else:
        with pytest.raises(TypeError):
            S.multiply_arr(a, b, np.empty(shape, dtype=dt))

    # adjustbenefit_arr（同じく）
    if dt not in (S.HIHOKENSHA, S.ICHIJIKIN):
        got = S.adjustbenefit_arr(s_b, a, np.empty(shape, dtype=dt))
        want = _one(lambda i, k: S.adjustbenefit(s_row[i], a[i, k]))
        assert _crc(got) == _crc(want), \
            "%s の adjustbenefit_arr が違う" % name
    else:
        with pytest.raises(TypeError):
            S.adjustbenefit_arr(s_b, a, np.empty(shape, dtype=dt))


def test_軸まとめ版が小さい型でも動く():
    """`_flat()` が `None` を返す型（GONEN・IZOKU・ICHIJIKIN）でも
    軸まとめ版は動くこと。

    1個ずつなら欄ごと版のほうが速いが、**軸がまとまるなら小さい型でも
    まとめたほうが速い**ので、`*_arr` は `_flat()` が `None` でも
    平べったい dtype を作って進む。そこが壊れていないか。
    """
    for dt in (S.GONEN, S.IZOKU, S.ICHIJIKIN):
        assert S._flat(dt) is None, "この型は欄ごと版のはず"
        n = dt.itemsize // 8
        a = np.zeros(4, dtype=dt)
        b = np.zeros(4, dtype=dt)
        a.view(np.float64).reshape(4, n)[:] = np.arange(4 * n).reshape(4, n)
        b.view(np.float64).reshape(4, n)[:] = 1.5

        got = S.add_arr(a, b, np.empty(4, dtype=dt))
        want = np.zeros(4, dtype=dt)
        for i in range(4):
            want[i] = S.add(a[i], b[i])
        assert _crc(got) == _crc(want), "%s の add_arr が違う" % dt.names

        got = S.scalar_arr(0.25, a, np.empty(4, dtype=dt))
        for i in range(4):
            want[i] = S.scalar(0.25, a[i])
        assert _crc(got) == _crc(want), "%s の scalar_arr が違う" % dt.names


@pytest.mark.parametrize("name", sorted(DTYPES))
def test_flat_viewで足し込んでも1個ずつaddするのとビット一致(name):
    """縮約（同じスロットへ何本も足す）を `flat_view` でやっても、
    `add` を1個ずつ呼ぶのと同じであること。

    `flat_view` の狙いは間接費を削ることで、**足す順は変えない**。
    ここで固定するのは「同じ順で同じ加算をしている」こと。
    順序を変えると値が変わる入力（大小の差が大きい値）をわざと使う。
    """
    dt = DTYPES[name]
    n = dt.itemsize // 8
    rng = np.random.default_rng(1000 + len(name))
    src = np.zeros((7, 5), dtype=dt)
    # 桁がばらばらの値。足す順を変えると丸めが変わる
    src.reshape(-1).view(np.float64)[:] = \
        rng.standard_normal(7 * 5 * n) * 10. ** rng.integers(-8, 8, 7 * 5 * n)

    # 1個ずつ（原本の形）
    want = np.zeros((), dtype=dt)
    for j in range(5):                  # 受給年齢が外
        for i in range(7):              # 年齢が内
            want = S.add(want, src[i, j])

    # flat_view で同じ順に足す
    got = np.zeros((), dtype=dt)
    dv = S.flat_view(got)
    sv = S.flat_view(src)
    for j in range(5):
        for i in range(7):
            np.add(dv, sv[i, j], out=dv)
    assert _crc(got) == _crc(want), "%s の flat_view 縮約が違う" % name

    # 逆順に足すと違う値になる（このテストが順序を見張れている証拠）
    rev = np.zeros((), dtype=dt)
    rv = S.flat_view(rev)
    for j in range(4, -1, -1):
        for i in range(6, -1, -1):
            np.add(rv, sv[i, j], out=rv)
    assert _crc(rev) != _crc(want), \
        "%s: 順序を変えても同じ値になった（入力が単純すぎる）" % name

    # 軸をまとめた足し込み（スロット i には j の順に1本ずつ）も同じ
    want2 = np.zeros(7, dtype=dt)
    for j in range(5):
        for i in range(7):
            want2[i] = S.add(want2[i], src[i, j])
    got2 = np.zeros(7, dtype=dt)
    dv2 = S.flat_view(got2)
    for j in range(5):
        np.add(dv2, sv[:, j], out=dv2)
    assert _crc(got2) == _crc(want2), "%s の軸まとめ縮約が違う" % name


def test_flat_viewは元を指す():
    """`flat_view` の戻りに書くと元の配列が変わること（0-d・void・配列）。"""
    a = np.zeros((3, 2), dtype=S.ROREI)
    S.flat_view(a)[1, 1, 0] = 7.5
    assert a[1, 1]["ninzu"] == 7.5
    S.flat_view(a[2, 0])[0] = 3.25            # void
    assert a[2, 0]["ninzu"] == 3.25
    z = np.zeros((), dtype=S.GONEN)
    S.flat_view(z)[1] = -1.0                  # 0-d、小さい型
    assert z["noufu"] == -1.0
    assert S.flat_view(a).shape == (3, 2, S.ROREI.itemsize // 8)


def test_nendokanの重みの控えが結果を変えない():
    """`_ndk_w1` の控えを使っても使わなくても同じであること。

    改定率は年度ごとにしか変わらないので重みベクトルを控えているが、
    控えが汚れると全部の年度が狂う。書き込み禁止にしてあることと、
    控えを消しても結果が変わらないことを押さえる。
    """
    a = _fill(S.ROREI, "rand", 800)
    b = _fill(S.ROREI, "rand", 801)

    w = S._ndk_w1(S.ROREI, 0.997, None)
    assert not w.flags.writeable, "控えが書き込みできてしまう"
    with pytest.raises(ValueError):
        w[1] = 0.

    first = _crc(S.nendokan(a, b, 0.997))
    again = _crc(S.nendokan(a, b, 0.997))       # 控えから引く
    S._NDK_W1.clear()
    fresh = _crc(S.nendokan(a, b, 0.997))       # 組み直す
    assert first == again == fresh
