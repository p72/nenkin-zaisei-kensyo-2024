/* ============================================================================
 * 差分テスト用ハーネス
 * ============================================================================
 * 目的: 原本の プログラム/国民年金/econ.c を **無修正でコンパイル** し、
 *       改定率と老齢基礎年金単価を CSV に吐き出させる。
 *       これを Python 実装（検証/verify_kaiteiritu.py）の出力と突き合わせ、
 *       移植が忠実かどうかを機械的に判定する。
 *
 * econ() が参照する外部依存のうち、本ハーネスが与えるもの:
 *   - fp_in[KEIZAI]        経済前提 CSV（引数で指定）
 *   - fp_out[KAITEI]       改定率の出力先
 *   - fp_out[PENSION]      年金単価の出力先
 *   - Full_Pension_Shonendo ほか  seid.c:15-95 と同じ初期化
 *   - TINSURA, Kisai_Shitasasae   cntl.c:46,58 / jikko_nat.sh:13 と同じ値
 *   - Option                      オプション試算なし
 *
 * seid() 本体は呼ばない（脱退率などの基礎率ファイルが同梱データに無いため）。
 * econ() が実際に読む初期値だけを seid.c と同じ手順で設定する。
 * ==========================================================================*/

#define MSEID_H_INCLUDED
#define MKISOSU_H_INCLUDED
#define MKISORITU_H_INCLUDED
#define MFILE_OPEN_H_INCLUDED
#define MECON_H_INCLUDED
#define MCNTL_H_INCLUDED
#define SNAPS_H_INCLUDED
#define OPTION_H_INCLUDED

#include <stdio.h>
#include <iostream>
#include <cstdlib>
#include <cstring>
#include "snaps.h"
#include "mseid.h"
#include "mcntl.h"
#include "mfile_open.h"
#include "mecon.h"
#include "mkisoritu.h"
#include "mkisosu.h"
#include "option.h"

void econ();

/* econ.c 内の CAL_START と同じ。ここより前は配列が未初期化なので出力しない */
#define CAL_START_OUT 2004

/* --- seid.c:15-95 のうち econ() が参照する部分だけを再現 ------------------ */
static void seid_minimal()
{
    for (int nendo = SHONENDO; nendo <= SAISHUNENDO; nendo++) {
        for (int seinendo = N_O_NENDO; seinendo <= SAISHUNENDO; seinendo++) {
            /* seid.c:21-25 */
            Kanou_Nensu[nendo - SHONENDO][seinendo - N_O_NENDO] =
                (seinendo <= 1941) ? (25 + seinendo - N_O_NENDO) : 40;
            /* seid.c:44 */
            Full_Pension_Shonendo[nendo - SHONENDO][seinendo - N_O_NENDO] = 780900.;
        }
    }
    Full_Pension_Fuka            = 2400.;    /* seid.c:58 */
    Kakyu_Tanka_12shi_Shonendo   = 224700.;  /* seid.c:60 */
    Kakyu_Tanka_3shiiko_Shonendo = 74900.;   /* seid.c:62 */
    Tanka_Shibou_Shonendo[0] = 120000.;      /* seid.c:64-71 */
    Tanka_Shibou_Shonendo[1] = 145000.;
    Tanka_Shibou_Shonendo[2] = 170000.;
    Tanka_Shibou_Shonendo[3] = 220000.;
    Tanka_Shibou_Shonendo[4] = 270000.;
    Tanka_Shibou_Shonendo[5] = 320000.;
    Tanka_Shibou_Shonendo[6] = 320000.;
    Tanka_Shibou_Fuka = 8500.;               /* seid.c:77 */
}

int main(int argc, char *argv[])
{
    if (argc < 3) {
        fprintf(stderr, "usage: %s <econ.csv> <out_dir>\n", argv[0]);
        return 2;
    }

    /* cntl.c:46 / jikko_nat.sh:13 */
    TINSURA = 1;
    /* cntl.c:58 */
    Kisai_Shitasasae = 0.80;
    /* オプション試算なし */
    Option = 0;

    fp_in[KEIZAI] = fopen(argv[1], "r");
    if (!fp_in[KEIZAI]) { perror(argv[1]); return 2; }

    char path[2048];
    snprintf(path, sizeof path, "%s/c_kaitei.csv", argv[2]);
    fp_out[KAITEI] = fopen(path, "w");
    snprintf(path, sizeof path, "%s/c_pension.csv", argv[2]);
    fp_out[PENSION] = fopen(path, "w");
    if (!fp_out[KAITEI] || !fp_out[PENSION]) { perror(argv[2]); return 2; }

    seid_minimal();

    econ();   /* ← 原本 econ.c を無修正で実行 */

    fclose(fp_out[KAITEI]);
    fclose(fp_out[PENSION]);
    fclose(fp_in[KEIZAI]);

    /* Python と比較しやすい形で、必要な系列だけを別途出力する。
     * 年度, 年齢, 単年改定率(kaiteiritu_tannen), 満額(Full_Pension) */
    snprintf(path, sizeof path, "%s/c_series.csv", argv[2]);
    FILE *fp = fopen(path, "w");
    fprintf(fp, "nendo,nenrei,tannen,full_pension\n");
    for (int nendo = CAL_START_OUT; nendo <= SAISHUNENDO; nendo++) {
        for (int nenrei = 0; nenrei <= MAX_ROREI_JUKYU; nenrei++) {
            double fp_val = (nendo >= SHONENDO)
                ? Full_Pension[nendo - SHONENDO][nenrei] : 0.0;
            fprintf(fp, "%d,%d,%.17g,%.17g\n", nendo, nenrei,
                    kaiteiritu_tannen[nendo - ECON_SHONENDO][nenrei], fp_val);
        }
    }
    fclose(fp);
    return 0;
}
