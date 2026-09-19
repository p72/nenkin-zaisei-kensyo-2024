# -*- sh -*-
# 実行領域 /suuri/rev2024 の置き場所を決める（source して使う）
# =============================================================================
# 原本は出力先も入力ファイルリストも `/suuri/rev2024` という絶対パスで持って
# いる（専用UNIXサーバの固定構成が前提だった名残。仕様書 §12.1）。
# ルート直下に書き込めない環境でも動くように、プレフィックスを付け替える。
#
#   SUURI_PREFIX 未設定  →  <リポジトリ>/work/suuri/rev2024   （既定・root不要）
#   SUURI_PREFIX=/       →  /suuri/rev2024                    （従来どおり）
#   SUURI_PREFIX=/mnt/d  →  /mnt/d/suuri/rev2024
#
# source する側で ROOT（リポジトリのルート）を先に定義しておくこと。
# 定義後に使える変数: PREFIX（末尾 / なし。/ 指定時は空文字）、SUURI
# =============================================================================

if [ -z "${ROOT:-}" ]; then
    echo "suuri_env.sh: ROOT が未定義です" >&2
    return 1 2>/dev/null || exit 1
fi

PREFIX="${SUURI_PREFIX-$ROOT/work}"
PREFIX="${PREFIX%/}"
SUURI="$PREFIX/suuri/rev2024"

# sed の区切りに | を使うので、パスに紛れると壊れる
case "$PREFIX" in
    *'|'*|*'&'*|*'\'*)
        echo "SUURI_PREFIX に | & \\ は使えません: $PREFIX" >&2
        return 1 2>/dev/null || exit 1 ;;
esac
