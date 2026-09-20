#!/bin/bash
# =============================================================================
# 厚生労働省の公表資料を取得して papers/ に展開する
# =============================================================================
# このリポジトリは厚生労働省の公表資料を**同梱していません**。正式な公開URLから
# 取得して SHA256 を照合します。取得先はすべて
#
#     令和6(2024)年財政検証（厚生労働省）
#     https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/nenkin/nenkin/zaisei-kensyo/index.html
#
# の配下です。厚生労働省ホームページのコンテンツは、特記のない限り
# 「公共データ利用規約（第1.0版）」（PDL1.0、CC BY 4.0 互換）に準拠した条件で
# 利用できます。詳細は LICENSE を参照してください。
#
# 使い方:
#   ./fetch.sh              必要なもの全部（約82MB）
#   ./fetch.sh program      ①〜⑤を動かすのに必要な最小限（15MB）
#   ./fetch.sh --check      取得済みファイルの SHA256 を照合するだけ
#   ./fetch.sh --list       取得するものの一覧を出すだけ
#
# 必要なもの: curl、sha256sum、python3（Shift_JIS のファイル名を扱うため）
#
# -----------------------------------------------------------------------------
# なぜ unzip ではなく python3 なのか
# -----------------------------------------------------------------------------
# ZIP のファイル名が Shift_JIS で、UTF-8 フラグ（汎用ビット 11）も立っていない
# ため、unzip では「File name too long」で失敗します。cp437 で読んだバイト列を
# cp932 として解釈し直す必要があります。
# =============================================================================
set -e

ROOT=$(cd "$(dirname "$0")" && pwd)
DEST="$ROOT/papers"
CACHE="${FETCH_CACHE:-$ROOT/.cache}"

# 取得物: 展開先ディレクトリ名|URL|SHA256|用途|必須か
ITEMS=(
"001365945|https://www.mhlw.go.jp/content/001365945.zip|5f653fad27c26f6ace87513b3775e6529e342c99ce69e9563cda7aea2dff2476|詳細結果等4 計算プログラム（111本）と入力データ（8,093本）|program"
"2024report_back|https://www.mhlw.go.jp/content/12500000/2024report_back.zip|73e4754eb2dfe087eab79aa3ed8619de6b9e3f1bae57aa1efa8b585e84ae015c|結果レポートの掲載表（検証/掲載表/ が使う）|verify"
"001286770|https://www.mhlw.go.jp/content/001286770.zip|42af199bf3fb3368fdfcd5708f26e71f8b731039302f01078862acb3f41b65c8|詳細結果等1 通常試算の財政見通し34本・被保険者数23本|verify"
"001286771|https://www.mhlw.go.jp/content/001286771.zip|882d7efc2998792f06dfdc5ac4a9247c161b306d6ef810858e8487d8c598ecb2|詳細結果等2 オプション試算の財政見通し92本・被保険者数27本|verify"
"001270447|https://www.mhlw.go.jp/content/001270447.zip|39a2333e14543967e1ff703cbd5aa830d50788f5b73c8f7df13a759e7ab56e30|詳細結果等3 給付と負担・分布推計ほか8表|verify"
)

# 2026年9月20日に取得したものの SHA256 です。厚生労働省は資料を予告なく差し替える
# ことがあるので（PDL1.0 の免責条項）、照合に失敗したら中身を確認してください。
# 差し替えを確認したら、このスクリプトのハッシュを更新して照合結果を記録します。

die() { echo "★ $*" >&2; exit 1; }

usage() {
    echo "使い方: $0 [all|program|--check|--list]"
    exit 1
}

list_items() {
    printf '%-18s %-9s %-10s %s\n' 展開先 区分 サイズ 用途
    printf '%s\n' '--------------------------------------------------------------------------------'
    for it in "${ITEMS[@]}"; do
        IFS='|' read -r name url sha use grp <<< "$it"
        sz=$(curl -sSI --max-time 30 "$url" 2>/dev/null \
             | awk 'tolower($1)=="content-length:"{v=$2+0; if(v>1e6) printf "%.0fMB", v/1e6; else printf "%.0fKB", v/1e3}' | tail -1)
        printf '%-18s %-9s %-10s %s\n' "$name" "$grp" "${sz:-?}" "$use"
    done
}

need() { command -v "$1" >/dev/null 2>&1 || die "$1 が見つかりません"; }

extract() {   # extract <zip> <展開先ディレクトリ>
    python3 - "$1" "$2" <<'PY'
import os, sys, zipfile

src, dest = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(src)
n_file = 0
for info in z.infolist():
    raw = info.filename
    # 汎用ビット 11（0x800）が立っていればファイル名は UTF-8。
    # 立っていなければ Shift_JIS なので cp437 → cp932 で読み直す。
    if info.flag_bits & 0x800:
        name = raw
    else:
        try:
            name = raw.encode('cp437').decode('cp932')
        except (UnicodeEncodeError, UnicodeDecodeError):
            name = raw
    # ZIP スリップ対策: 展開先から出るパスは受け付けない
    path = os.path.normpath(os.path.join(dest, name))
    if not (path + os.sep).startswith(os.path.join(os.path.abspath(dest), '')):
        raise SystemExit(f'展開先の外を指すエントリがあります: {name!r}')
    if name.endswith('/'):
        os.makedirs(path, exist_ok=True)
        continue
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(z.read(info))
    n_file += 1
print(f'    {n_file} ファイル展開')
PY
}

fetch_one() {   # fetch_one <name> <url> <sha256> <use>
    local name="$1" url="$2" sha="$3" use="$4"
    local zip="$CACHE/$name.zip"

    echo
    echo "==== $name  $use"

    if [ -f "$zip" ] && [ "$(sha256sum "$zip" | cut -d' ' -f1)" = "$sha" ]; then
        echo "    取得済み（SHA256 一致）"
    else
        [ -f "$zip" ] && echo "    キャッシュのハッシュが合わないので取り直します"
        echo "    取得中 $url"
        curl -fSL --retry 4 --retry-delay 2 --max-time 900 -o "$zip.part" "$url" \
            || die "$name の取得に失敗しました"
        mv "$zip.part" "$zip"
        local got
        got=$(sha256sum "$zip" | cut -d' ' -f1)
        if [ "$got" != "$sha" ]; then
            echo "    期待 $sha" >&2
            echo "    実際 $got" >&2
            die "$name の SHA256 が合いません。厚生労働省が資料を差し替えた可能性があります。
    中身を確認し、正しいと判断できたら fetch.sh のハッシュを更新してください。"
        fi
        echo "    SHA256 一致 $got"
    fi

    rm -rf "$DEST/$name"
    mkdir -p "$DEST/$name"
    extract "$zip" "$DEST/$name"
}

check_only() {
    local bad=0
    for it in "${ITEMS[@]}"; do
        IFS='|' read -r name url sha use grp <<< "$it"
        local zip="$CACHE/$name.zip"
        if [ ! -f "$zip" ]; then
            printf '%-18s 未取得\n' "$name"
            continue
        fi
        local got
        got=$(sha256sum "$zip" | cut -d' ' -f1)
        if [ "$got" = "$sha" ]; then
            printf '%-18s 一致\n' "$name"
        else
            printf '%-18s ★不一致 (%s)\n' "$name" "$got"
            bad=1
        fi
    done
    return $bad
}

case "${1:-all}" in
    --list) list_items; exit 0 ;;
    --check) need sha256sum; check_only; exit $? ;;
    all)     WANT=all ;;
    program) WANT=program ;;
    -h|--help) usage ;;
    *) usage ;;
esac

need curl; need sha256sum; need python3
mkdir -p "$CACHE" "$DEST"

for it in "${ITEMS[@]}"; do
    IFS='|' read -r name url sha use grp <<< "$it"
    if [ "$WANT" = program ] && [ "$grp" != program ]; then continue; fi
    fetch_one "$name" "$url" "$sha" "$use"
done

echo
echo "==== 完了"
echo "  展開先 $DEST"
du -sh "$DEST"/* 2>/dev/null | sed 's/^/  /'
echo
echo "  出典：厚生労働省ホームページ「令和6(2024)年財政検証」"
echo "  https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/nenkin/nenkin/zaisei-kensyo/index.html"
echo
if [ "$WANT" = all ]; then
    echo "  次は 検証/実行/run_pipeline.sh 3001 で通しに流せます。"
else
    echo "  次は 検証/実行/run_pipeline.sh 3001 で通しに流せます。"
    echo "  公表値との照合もするなら ./fetch.sh で残りも取得してください。"
fi
