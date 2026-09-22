#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""非公開リポジトリから公開リポジトリへ写す（照合つき）
=====================================================
このプロジェクトは2つのリポジトリに分かれている。

    p72/0919nenkin                 非公開・作業場
      ├ papers/ を git にコミット済み  → 原本をいつでもビルドできる
      └ work/（6.4GB、追跡外）        → ビット一致を測れる

    p72/nenkin-zaisei-kensyo-2024   公開・成果物の置き場
      └ papers/ は同梱せず fetch.sh で取得する

**追跡ファイルの集合は `EXCLUDE` を除いて完全に一致している。** つまり

    公開側の追跡ファイル ＝ 非公開側の追跡ファイル − `EXCLUDE`

これが同期の規則。手でコピーすると写し漏れや片側だけ直した状態に
気づけないので、この規則を機械にやらせる。

やること
--------
1. `git ls-files` で**追跡ファイルだけ**を集める（`__pycache__` や
   `.pytest_cache` が混ざらない）。`papers/` は除く
2. 写す前に検査する。引っかかったら**1バイトも写さずに止まる**
   - 秘密らしきもの（トークン・鍵・40桁hex の API キー・メールアドレス）
   - 環境固有の絶対パス（利用者のホーム配下など）
3. 写す
4. `filecmp` で**全件バイト照合**する
5. 公開側にだけある追跡ファイル（非公開側で消したもの）を報告する
6. Markdown の**相対リンク**が公開側の木で解決するか検査する

コミットと push はやらない。`git diff` を人が見てから決める。

使い方
------
    # 写す
    python3 検証/実行/sync_public.py ~/nenkin-zaisei-kensyo-2024

    # 写さずに、ずれていないかだけ見る
    python3 検証/実行/sync_public.py ~/nenkin-zaisei-kensyo-2024 --check

    # 公開側にだけある追跡ファイルも消す
    python3 検証/実行/sync_public.py ~/nenkin-zaisei-kensyo-2024 --prune

`--check` はずれていれば終了コード1を返すので、公開の前の確認に使える。

検査に引っかかったとき
----------------------
`--allow-scan` で検査全体を飛ばせるが、**公開リポジトリに出す前提なので
基本は直すこと。** 実際にこの検査で2件見つかっている。

- `検証/移植/emp_kyufu/fileio.py` の `_ORIG_BASE`（宣言だけのデッドコード）
- `検証/図/make_chart.py` の `main(out=…)` の既定値（`HERE` を使う形に直した）

どうしても引っかかるのが正しい行（このファイルのパターン定義そのものなど）
には、行末に `sync-public:scan-ignore` と書くとその**1行だけ**飛ばす。
ファイル全体を飛ばさないのは、そのファイルに本物の秘密が混ざったときに
見逃さないため。
"""
import argparse
import filecmp
import os
import re
import shutil
import subprocess
import sys

# 公開側に写さないもの（先頭一致）
#
# `papers/`       公開側は同梱せず `fetch.sh` で取得する方針
# `CLAUDE.md`     非公開側での作業の約束。`papers/` も `work/` も無い公開側では
#                 内容が成り立たないので写さない
# `検証/高速版/`  高速版（数式モデル実装）の計画と作業場。承認・完成するまで
#                 公開しない
# `検証/2号廃止/` 第2号まで廃止した場合の試算。18.3% を据え置いたままなので
#                 結果が極端になる。負担中立版を作るまで公開しない
# `検証/債務/`    既裁定債務・既発生債務の給付現価。2号廃止の議論の材料として
#                 計算したもので、単体では文脈が足りない。公開しない
EXCLUDE = ("papers/", "CLAUDE.md", "検証/高速版/",
           "検証/2号廃止/", "検証/債務/")

# 写す前の検査。実コーパスで誤検出0を確認したパターン。
# 40桁hex は e-Stat の APP ID の形。`fetch.sh` の SHA256 は64桁なので
# 単語境界で引っかからない（実測で確認済み）。
SECRET_PATTERNS = (
    ("40桁hex（API キーの形）",
     re.compile(r'\b[0-9a-f]{40}\b')),
    ("GitHub トークン",
     re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}')),
    ("AWS アクセスキー",
     re.compile(r'AKIA[0-9A-Z]{16}')),
    ("秘密鍵",
     re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ("key/token/password への代入",
     re.compile(r'(?i)(api[_-]?key|app[_-]?id|access[_-]?token|secret'
                r'|password|passwd)\s*[:=]\s*["\']?[A-Za-z0-9_\-]{16,}')),
    ("メールアドレス",
     re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')),
    ("環境固有の絶対パス",
     re.compile(r'/home/[a-z]|/root/|/tmp/claude|/Users/')),  # sync-public:scan-ignore
)

MD_LINK = re.compile(r'\[[^\]]*\]\(([^)\s]+)\)')

# この印が書かれた行は検査を飛ばす。上のパターン定義そのものが
# 引っかかるのを避けるため（ファイル全体を飛ばすと、そのファイルに
# 本物の秘密が混ざったとき見逃すので、行単位にしてある）。
SCAN_IGNORE = "sync-public:scan-ignore"


def run(args, cwd):
    """`git` を呼ぶ。失敗したら止まる。"""
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        die("%s が失敗した（%s）:\n%s" % (" ".join(args), cwd, r.stderr))
    return r.stdout


def die(msg):
    sys.stderr.write("\n【中止】%s\n" % msg)
    raise SystemExit(2)


def tracked(root):
    """追跡ファイルの一覧（`papers/` などを除く）。"""
    out = run(["git", "-c", "core.quotepath=off", "ls-files"], root)
    return sorted(f for f in out.split("\n")
                  if f and not f.startswith(EXCLUDE))


def is_text(path):
    """先頭を見てテキストか判定する（NUL があれば binary 扱い）。"""
    try:
        with open(path, "rb") as fp:
            return b"\0" not in fp.read(4096)
    except OSError:
        return False


def scan(root, files):
    """写す前の検査。見つかったものを (種類, ファイル, 行, 抜粋) で返す。"""
    hits = []
    for f in files:
        p = os.path.join(root, f)
        if not os.path.isfile(p) or not is_text(p):
            continue
        with open(p, encoding="utf-8", errors="replace") as fp:
            lines = fp.read().split("\n")
        for ln, line in enumerate(lines, 1):
            if SCAN_IGNORE in line:
                continue
            for name, pat in SECRET_PATTERNS:
                for m in pat.finditer(line):
                    hits.append((name, f, ln, m.group(0)[:70]))
    return hits


def check_links(root, files):
    """Markdown の相対リンクが `root` の木で解決するか。"""
    bad = []
    for f in files:
        if not f.endswith(".md"):
            continue
        p = os.path.join(root, f)
        if not os.path.isfile(p):
            continue
        with open(p, encoding="utf-8", errors="replace") as fp:
            txt = fp.read()
        base = os.path.dirname(f)
        for target in MD_LINK.findall(txt):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            rel = os.path.normpath(os.path.join(base, target.split("#")[0]))
            if not os.path.exists(os.path.join(root, rel)):
                bad.append((f, target, rel))
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="非公開リポジトリから公開リポジトリへ写す（照合つき）")
    ap.add_argument("dest", help="公開リポジトリのパス")
    ap.add_argument("--check", action="store_true",
                    help="写さずに、ずれていないかだけ見る（ずれていれば終了コード1）")
    ap.add_argument("--prune", action="store_true",
                    help="公開側にだけある追跡ファイルを消す")
    ap.add_argument("--allow-scan", action="store_true",
                    help="秘密・環境固有パスの検査に引っかかっても続ける")
    a = ap.parse_args(argv)

    here = os.path.dirname(os.path.abspath(__file__))
    src = run(["git", "rev-parse", "--show-toplevel"], here).strip()
    dest = os.path.abspath(os.path.expanduser(a.dest))
    if not os.path.isdir(os.path.join(dest, ".git")):
        die("%s は git リポジトリではない" % dest)
    if os.path.realpath(src) == os.path.realpath(dest):
        die("写し元と写し先が同じ（%s）" % src)

    print("写し元: %s" % src)
    print("写し先: %s" % dest)

    # 写し先に未コミットの変更があると、写した差分と混ざって見分けが
    # つかなくなる。`--check` は読むだけなので許す。
    dirty = run(["git", "status", "--porcelain"], dest).strip()
    if dirty and not a.check:
        die("写し先に未コミットの変更がある。先に片付けること:\n%s"
            % dirty[:2000])

    files = tracked(src)
    print("\n追跡ファイル %d 本（`%s` を除く）"
          % (len(files), "` `".join(EXCLUDE)))

    # ---- 1. 写す前の検査 ----------------------------------------
    hits = scan(src, files)
    if hits:
        print("\n■ 検査に引っかかった（%d 件）" % len(hits))
        for name, f, ln, s in hits:
            print("  [%s] %s:%d  %s" % (name, f, ln, s))
        if not a.allow_scan:
            die("公開リポジトリに出すので、上を直してから写すこと。\n"
                "        どうしても写すなら --allow-scan")
        print("  （--allow-scan が付いているので続ける）")
    else:
        print("検査: 秘密・環境固有パスは見つからなかった")

    # ---- 2. 写す／比べる ----------------------------------------
    copied = same = 0
    diff = []
    for f in files:
        s = os.path.join(src, f)
        d = os.path.join(dest, f)
        if not os.path.isfile(s):
            continue
        if os.path.isfile(d) and filecmp.cmp(s, d, shallow=False):
            same += 1
            continue
        if a.check:
            diff.append(f)
            continue
        os.makedirs(os.path.dirname(d) or ".", exist_ok=True)
        shutil.copyfile(s, d)     # バイトをそのまま写す（`* -text` を守る）
        copied += 1

    # ---- 3. 全件バイト照合 --------------------------------------
    if not a.check:
        ng = [f for f in files
              if os.path.isfile(os.path.join(src, f))
              and not filecmp.cmp(os.path.join(src, f),
                                  os.path.join(dest, f), shallow=False)]
        if ng:
            die("写したのにバイトが一致しない %d 本:\n  %s"
                % (len(ng), "\n  ".join(ng[:20])))
        print("\n写した %d 本 / 既に同じ %d 本 → 全 %d 本がバイト一致"
              % (copied, same, len(files)))
    else:
        if diff:
            print("\n■ 公開側と中身が違う（%d 本）" % len(diff))
            for f in diff[:40]:
                print("  %s" % f)
            if len(diff) > 40:
                print("  … 他 %d 本" % (len(diff) - 40))
        else:
            print("\n全 %d 本がバイト一致（ずれなし）" % len(files))

    # ---- 4. 公開側にだけある追跡ファイル ------------------------
    extra = sorted(set(tracked(dest)) - set(files))
    if extra:
        print("\n■ 公開側にだけある追跡ファイル（%d 本）" % len(extra))
        for f in extra:
            print("  %s" % f)
        if a.prune and not a.check:
            for f in extra:
                run(["git", "rm", "-q", "--", f], dest)
            print("  → --prune が付いているので git rm した")
        else:
            print("  （非公開側で消したものならこれも消す: --prune）")

    # ---- 5. 相対リンクの検査 ------------------------------------
    target = src if a.check else dest
    bad = check_links(target, files)
    if bad:
        print("\n■ 相対リンクが解決しない（%d 件・%s の木で検査）"
              % (len(bad), "写し元" if a.check else "写し先"))
        for f, t, rel in bad:
            print("  %s -> %s（解決先 %s）" % (f, t, rel))
    else:
        print("相対リンク: 切れなし")

    # ---- まとめ --------------------------------------------------
    ok = not bad and not (a.check and diff)
    if a.check:
        print("\n%s" % ("ずれなし。" if ok and not extra
                        else "ずれている（上を見ること）。"))
        return 0 if (ok and not extra and not diff) else 1

    print("\n次にやること:")
    print("  cd %s" % dest)
    print("  git status && git diff")
    print("  git add -A && git commit && git push -u origin main")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
