/* ③国民年金のグローバル変数を原本から取り出すハーネス
 * ====================================================
 * 原本の .c を**無修正でコンパイルしてリンク**し、`main.c` の代わりに
 * この `main()` を使う。段階（`cntl` → `file_open` → `seid` → `econ`
 * → …）を第1引数で指定して、そこまで通したあとのグローバルを
 * CRC32 で出す。
 *
 *   ./h <stage> <argv1> … <argv15>
 *
 *     stage  cntl / seid
 *     argv   原本の `main.c` に渡すものと同じ15個
 *
 * 出力は1行1変数で（原本の `cout` と混ざらないよう `## ` を付ける）
 *
 *     ## <名前> <要素数> <CRC32(16進)> <先頭の非ゼロ要素の %a>
 *     ## <名前> int <値> -
 *     ## <名前> dbl <%a> -
 *     ## <名前> str <文字列> -
 *
 * CRC32 は **C の行優先**で 8 バイトずつ食わせる。NumPy の
 * `arr.tobytes()` と同じ並びなので、Python 側と突き合わせられる。
 *
 * `main.c` と同じ順でガードのマクロを立ててから include するので、
 * この翻訳単位がグローバルの実体を持つ。
 */
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

using namespace std;

/* ---- CRC32（zlib と同じ多項式・同じ初期値）---- */
static unsigned int crc_table[256];
static bool crc_ready = false;

static void crc_init(void) {
	for (unsigned int i = 0; i < 256; i++) {
		unsigned int c = i;
		for (int k = 0; k < 8; k++)
			c = (c & 1) ? 0xedb88320u ^ (c >> 1) : (c >> 1);
		crc_table[i] = c;
	}
	crc_ready = true;
}

struct Crc {
	unsigned int c;
	long long n;
	double first;
	bool have_first;
	Crc() : c(0xffffffffu), n(0), first(0.0), have_first(false) {
		if (!crc_ready) crc_init();
	}
	void add(double v) {
		unsigned char *p = (unsigned char *)&v;
		for (int i = 0; i < 8; i++)
			c = crc_table[(c ^ p[i]) & 0xff] ^ (c >> 8);
		n++;
		if (!have_first && v != 0.0) { first = v; have_first = true; }
	}
	unsigned int value(void) const { return c ^ 0xffffffffu; }
};

/* 素の double 配列は連続しているので、先頭と個数で渡す。
 * `struct` の配列も double だけで詰め物が無いので同じ扱いでよい
 * （`sizeof(struct)` が欄数 × 8 であることは下で確かめる）。 */
static void report_mem(const char *name, const double *p, long long n) {
	Crc h;
	for (long long i = 0; i < n; i++) h.add(p[i]);
	printf("## %s %lld %08x", name, h.n, h.value());
	if (h.have_first) printf(" %a\n", h.first);
	else printf(" -\n");
}

#define REPORT(a) report_mem(#a, (const double *)&(a), \
                             (long long)(sizeof(a) / sizeof(double)))

/* 種別ごとに `s2_Hihokensha` のような名前を作る */
static char nmbuf[64];
static const char *nm(const char *pfx, const char *name) {
	snprintf(nmbuf, sizeof nmbuf, "%s%s", pfx, name);
	return nmbuf;
}

static void report_int(const char *name, int v) {
	printf("## %s int %d -\n", name, v);
}
static void report_dbl(const char *name, double v) {
	printf("## %s dbl %a -\n", name, v);
}
static void report_str(const char *name, const char *v) {
	printf("## %s str %s -\n", name, v);
}

/* `sizeof(struct)` が「欄数 × 8」であること（詰め物が無いこと）を
 * 確かめて出す。Python 側の構造化 dtype と並びが一致する前提。 */
static void report_sizes(void) {
	report_int("sizeof_hihokensha", (int)sizeof(struct hihokensha));
	report_int("sizeof_rorei", (int)sizeof(struct rorei));
	report_int("sizeof_rorei_kyu", (int)sizeof(struct rorei_kyu));
	report_int("sizeof_gonen", (int)sizeof(struct gonen));
	report_int("sizeof_shogai", (int)sizeof(struct shogai));
	report_int("sizeof_izoku", (int)sizeof(struct izoku));
	report_int("sizeof_kafu", (int)sizeof(struct kafu));
	report_int("sizeof_ichijikin", (int)sizeof(struct ichijikin));
}

int main(int argc, char *argv[]) {
	if (argc < 2) {
		fprintf(stderr, "usage: %s <stage> <argv1> ... <argv15>\n", argv[0]);
		return 2;
	}
	string stage = argv[1];

	/* `cntl( argc , argv )` は `argc != 16` を見るので、
	 * 段階の分だけずらして渡す */
	cntl(argc - 1, argv + 1);

	if (stage == "cntl") {
		report_str("KOKUNEN", KOKUNEN);
		report_str("ECON", ECON);
		report_str("SOTOWAKU", SOTOWAKU);
		report_str("SOTOWAKU_JURAI", SOTOWAKU_JURAI);
		report_str("Version", Version);
		report_str("BIRTHFILE", BIRTHFILE);
		report_str("DEATH", DEATH);
		report_int("Kako_Saimu", Kako_Saimu);
		report_int("TINSURA", TINSURA);
		report_int("Kugiri_Nendo", Kugiri_Nendo);
		report_int("Jyukyusha_Nomi", Jyukyusha_Nomi);
		report_dbl("Kisai_Shitasasae", Kisai_Shitasasae);
		report_int("Part", Part);
		report_int("Part_Year", Part_Year);
		report_int("Option", Option);
		report_int("OPTION_START", OPTION_START);
		report_int("OP_HIKIAGE_KANKAKU", OP_HIKIAGE_KANKAKU);
		report_sizes();
		return 0;
	}

	if (stage == "seid") {
		seid();
		REPORT(Kanou_Nensu);
		REPORT(Full_Pension_Shonendo);
		report_dbl("Full_Pension_Fuka", Full_Pension_Fuka);
		report_dbl("Kakyu_Tanka_12shi_Shonendo", Kakyu_Tanka_12shi_Shonendo);
		report_dbl("Kakyu_Tanka_3shiiko_Shonendo",
		           Kakyu_Tanka_3shiiko_Shonendo);
		REPORT(Tanka_Shibou_Shonendo);
		report_dbl("Tanka_Shibou_Fuka", Tanka_Shibou_Fuka);
		REPORT(Hokenryou_Wariai);
		REPORT(Shogai_Bairitu);
		REPORT(Kokko_Wariai);
		report_sizes();
		return 0;
	}

	if (stage == "econ") {
		/* `main.c` と同じ順で file_open → seid → econ。
		 * `econ()` は `fp_in[KEIZAI]` を読み、`fp_out[KAITEI]` と
		 * `fp_out[PENSION]` に書く。 */
		file_open(argv[2], fp_in, infile_name);
		file_open(argv[3], fp_out, outfile_name);
		seid();
		econ();
		REPORT(kaiteiritu_tannen);
		REPORT(Full_Pension);
		REPORT(Kakyu_Tanka_12shi);
		REPORT(Kakyu_Tanka_3shiiko);
		REPORT(Tanka_Shibou);
		REPORT(Kanou_Nensu);
		REPORT(Full_Pension_Shonendo);
		report_sizes();
		/* 出力を閉じる（原本は `main()` を抜けるとき OS が閉じる。
		 * `file_close()` は宣言だけで定義が無い） */
		for (int i = 0; i < OUTFILE_NUM; i++)
			if (fp_out[i] != NULL) fclose(fp_out[i]);
		return 0;
	}

	if (stage == "waku" || stage == "kaizen") {
		/* `main.c` と同じ順で file_open → seid → econ → waku → kaizen。
		 * `waku()` は外枠（①の結果）を、`kaizen()` は生命表と
		 * 有配偶率を読む。 */
		file_open(argv[2], fp_in, infile_name);
		file_open(argv[3], fp_out, outfile_name);
		seid();
		econ();
		waku();
		REPORT(Sotowaku);
		REPORT(Sotowaku_2gou);
		REPORT(Sotowaku_Jurai);
		if (stage == "kaizen") {
			kaizen();
			REPORT(q);
			REPORT(Izoku_Keinen);
		}
		report_sizes();
		for (int i = 0; i < OUTFILE_NUM; i++)
			if (fp_out[i] != NULL) fclose(fp_out[i]);
		return 0;
	}

	if (stage == "noufuritu") {
		file_open(argv[2], fp_in, infile_name);
		file_open(argv[3], fp_out, outfile_name);
		seid();
		econ();
		waku();
		kaizen();
		noufuritu();
		REPORT(Noufuritu);
		REPORT(Noufuritu_Fuka);
		REPORT(Hiho_Sankyu_Sum);
		REPORT(Hiho_Ikukyu);
		REPORT(Hiho_Ikukyu_Sum);
		report_sizes();
		for (int i = 0; i < OUTFILE_NUM; i++)
			if (fp_out[i] != NULL) fclose(fp_out[i]);
		return 0;
	}

	if (stage == "dtst") {
		/* `main.c` と同じ順で、種別ループの `dtst( shubetu )` まで。
		 * 種別 2・3・5・6 を順に通し、そのたびに配列を出す
		 * （`*_Nendomatu` は種別ごとに上書きされるので途中を見る）。 */
		file_open(argv[2], fp_in, infile_name);
		file_open(argv[3], fp_out, outfile_name);
		seid();
		econ();
		waku();
		kaizen();
		noufuritu();
		int shub[4] = {2, 3, 5, 6};
		for (int i = 0; i < 4; i++) {
			dtst(shub[i]);
			char p[32];
			snprintf(p, sizeof p, "s%d_", shub[i]);
			report_mem(nm(p, "Hihokensha"),
			           (const double *)&Hihokensha,
			           sizeof(Hihokensha) / sizeof(double));
			report_mem(nm(p, "Taikisha"), (const double *)&Taikisha,
			           sizeof(Taikisha) / sizeof(double));
			report_mem(nm(p, "Rorei_Nendomatu"),
			           (const double *)&Rorei_Nendomatu,
			           sizeof(Rorei_Nendomatu) / sizeof(double));
			report_mem(nm(p, "Rorei_Ichibu_Nendomatu"),
			           (const double *)&Rorei_Ichibu_Nendomatu,
			           sizeof(Rorei_Ichibu_Nendomatu) / sizeof(double));
			report_mem(nm(p, "Rorei_Kyu_Nendomatu"),
			           (const double *)&Rorei_Kyu_Nendomatu,
			           sizeof(Rorei_Kyu_Nendomatu) / sizeof(double));
			report_mem(nm(p, "Turo_Kyu_Nendomatu"),
			           (const double *)&Turo_Kyu_Nendomatu,
			           sizeof(Turo_Kyu_Nendomatu) / sizeof(double));
			report_mem(nm(p, "Gonen_Nendomatu"),
			           (const double *)&Gonen_Nendomatu,
			           sizeof(Gonen_Nendomatu) / sizeof(double));
			report_mem(nm(p, "Shogai_Ippan_Nendomatu"),
			           (const double *)&Shogai_Ippan_Nendomatu,
			           sizeof(Shogai_Ippan_Nendomatu) / sizeof(double));
			report_mem(nm(p, "Shogai_20mae_Nendomatu"),
			           (const double *)&Shogai_20mae_Nendomatu,
			           sizeof(Shogai_20mae_Nendomatu) / sizeof(double));
			report_mem(nm(p, "Shogai_Kyu_Nendomatu"),
			           (const double *)&Shogai_Kyu_Nendomatu,
			           sizeof(Shogai_Kyu_Nendomatu) / sizeof(double));
			report_mem(nm(p, "Izoku_Tuma_Nendomatu"),
			           (const double *)&Izoku_Tuma_Nendomatu,
			           sizeof(Izoku_Tuma_Nendomatu) / sizeof(double));
			report_mem(nm(p, "Izoku_Otto_Nendomatu"),
			           (const double *)&Izoku_Otto_Nendomatu,
			           sizeof(Izoku_Otto_Nendomatu) / sizeof(double));
			report_mem(nm(p, "Izoku_Ko_Nendomatu"),
			           (const double *)&Izoku_Ko_Nendomatu,
			           sizeof(Izoku_Ko_Nendomatu) / sizeof(double));
			report_mem(nm(p, "Kafu_Nendomatu"),
			           (const double *)&Kafu_Nendomatu,
			           sizeof(Kafu_Nendomatu) / sizeof(double));
			report_mem(nm(p, "Kafu_Kyu_Nendomatu"),
			           (const double *)&Kafu_Kyu_Nendomatu,
			           sizeof(Kafu_Kyu_Nendomatu) / sizeof(double));
			report_mem(nm(p, "Ichijikin_Nendomatu"),
			           (const double *)&Ichijikin_Nendomatu,
			           sizeof(Ichijikin_Nendomatu) / sizeof(double));
		}
		report_sizes();
		for (int i = 0; i < OUTFILE_NUM; i++)
			if (fp_out[i] != NULL) fclose(fp_out[i]);
		return 0;
	}

	if (stage == "kiso") {
		/* `main.c` と同じ順で、種別ループの `kiso( shubetu )` まで。
		 * `dtst()` も間に入れる（`kiso()` の前に必ず呼ばれるので）。
		 * 種別 2・3・5・6 を順に通し、そのたびに基礎率を出す。
		 * `Shikkenritu_Otto` は種別 5 のときに種別 2 が読んだ
		 * `Shikkenritu_Tuma` を使うので、順に通すことが大事。 */
		file_open(argv[2], fp_in, infile_name);
		file_open(argv[3], fp_out, outfile_name);
		seid();
		econ();
		waku();
		kaizen();
		noufuritu();
		int shub[4] = {2, 3, 5, 6};
		for (int i = 0; i < 4; i++) {
			dtst(shub[i]);
			kiso(shub[i]);
			char p[32];
			snprintf(p, sizeof p, "s%d_", shub[i]);
#define K(v) report_mem(nm(p, #v), (const double *)&v, \
                        sizeof(v) / sizeof(double))
			K(Dattairyoku_Gokei);
			K(Dattairyoku_Shibou);
			K(Saikanyuritu);
			K(Hassei_Wariai_Rorei);
			K(Hasseiryoku_Shogai);
			K(Hassei_Wariai_20mae);
			K(Hassei_Wariai_Tuma);
			K(Hassei_Wariai_Otto);
			K(Hassei_Wariai_Ko);
			K(Hassei_Wariai_Kafu);
			K(Hassei_Wariai_Shibou);
			K(Tokyu_Wariai_Ippan);
			K(Tokyu_Wariai_20mae);
			K(Kakyu_Wariai_Ippan_12shi);
			K(Kakyu_Wariai_Ippan_3shiiko);
			K(Kakyu_Wariai_20mae_12shi);
			K(Kakyu_Wariai_20mae_3shiiko);
			K(Kakyu_Wariai_Tuma_12shi);
			K(Kakyu_Wariai_Tuma_3shiiko);
			K(Kakyu_Wariai_Otto_12shi);
			K(Kakyu_Wariai_Otto_3shiiko);
			K(Kakyu_Wariai_Ko_12shi);
			K(Kakyu_Wariai_Ko_3shiiko);
			K(Sokan_Tuma);
			K(Sokan_Otto);
			K(Sokan_Ko);
			K(Sokan_Kafu);
			K(Shikkenritu_Rorei);
			K(Shikkenritu_Ippan);
			K(Shikkenritu_20mae);
			K(Shikkenritu_Tuma);
			K(Shikkenritu_Otto);
			K(Shikkenritu_Ko);
			K(Shikkenritu_Kafu);
			K(Shikyuritu_Rorei);
			K(Shikyuritu_Rorei_Kyu);
			K(Shikyuritu_Turo_Kyu);
			K(Shikyuritu_Gonen);
			K(Shikyuritu_Shogai_Ippan);
			K(Shikyuritu_Shogai_Ippan_keinen);
			K(Shikyuritu_Shogai_20mae);
			K(Shikyuritu_Shogai_20mae_keinen);
			K(Shikyuritu_Shogai_Kyu);
			K(Shikyuritu_Tuma);
			K(Shikyuritu_Otto);
			K(Shikyuritu_Ko);
			K(Shikyuritu_Kafu);
			K(Kakudai_Ichibu);
			K(Waribikiritu);
			K(Kyufu_ritu);
			K(Kyufu_ritu1);
			K(Kyufu_ritu2);
#undef K
		}
		report_sizes();
		for (int i = 0; i < OUTFILE_NUM; i++)
			if (fp_out[i] != NULL) fclose(fp_out[i]);
		return 0;
	}

	if (stage == "shke") {
		/* `main.c` と同じ順で、種別ループの `shke( SUIKEISHONENDO ,
		 * shubetu )` まで（`siml()` は呼ばない＝足元の1年度だけ）。
		 * `shke()` は `+=` で足し込むので、種別ごとに出す。 */
		file_open(argv[2], fp_in, infile_name);
		file_open(argv[3], fp_out, outfile_name);
		seid();
		econ();
		waku();
		kaizen();
		noufuritu();
		int shub[4] = {2, 3, 5, 6};
		for (int i = 0; i < 4; i++) {
			dtst(shub[i]);
			kiso(shub[i]);
			shke(SUIKEISHONENDO, shub[i]);
			char p[32];
			snprintf(p, sizeof p, "s%d_", shub[i]);
#define S(v) report_mem(nm(p, #v), (const double *)&v, \
                        sizeof(v) / sizeof(double))
			S(Hiho_Kei);
			S(Hiho_Noufu);
			S(Fuka_Hiho);
			S(Hiho_Noufu_P);
			S(Fuka_Hiho_P);
			S(Hiho_Menjo);
			S(Hiho_Menjo_P);
			S(Rorei);
			S(Rorei_Kyu);
			S(Turo_Kyu);
			S(Gonen);
			S(Shogai_Ippan);
			S(Shogai_20mae);
			S(Shogai_Kyu);
			S(Izoku_Tuma);
			S(Izoku_Otto);
			S(Izoku_Ko);
			S(Kafu);
			S(Kafu_Kyu);
			S(Ichijikin);
#undef S
		}
		report_sizes();
		for (int i = 0; i < OUTFILE_NUM; i++)
			if (fp_out[i] != NULL) fclose(fp_out[i]);
		return 0;
	}

	if (stage == "siml") {
		/* `main.c` と同じ順で、種別ループを丸ごと通す。
		 * 何年度まで回すかは環境変数 SIML_YEARS で決める（既定 3年）。
		 * `siml()` は前年度から作るので年度を飛ばせない。 */
		int years = 3;
		{ const char *e = getenv("SIML_YEARS");
		  if (e != NULL) years = atoi(e); }
		file_open(argv[2], fp_in, infile_name);
		file_open(argv[3], fp_out, outfile_name);
		seid();
		econ();
		waku();
		kaizen();
		noufuritu();
		int shub[4] = {2, 3, 5, 6};
		for (int i = 0; i < 4; i++) {
			dtst(shub[i]);
			kiso(shub[i]);
			shke(SUIKEISHONENDO, shub[i]);
			for (int nendo = SUIKEISHONENDO + 1;
			     nendo <= SUIKEISHONENDO + years; nendo++) {
				siml(nendo, shub[i]);
				shke(nendo, shub[i]);
			}
			char p[32];
			snprintf(p, sizeof p, "s%d_", shub[i]);
#define M(v) report_mem(nm(p, #v), (const double *)&v, \
                        sizeof(v) / sizeof(double))
			M(Hihokensha);
			M(Taikisha);
			M(Hihokensha2);
			M(Rorei_Nendomatu);
			M(Rorei_Ichibu_Nendomatu);
			M(Rorei_Kyu_Nendomatu);
			M(Turo_Kyu_Nendomatu);
			M(Gonen_Nendomatu);
			M(Shogai_Ippan_Nendomatu);
			M(Shogai_20mae_Nendomatu);
			M(Shogai_Kyu_Nendomatu);
			M(Izoku_Tuma_Nendomatu);
			M(Izoku_Otto_Nendomatu);
			M(Izoku_Ko_Nendomatu);
			M(Kafu_Nendomatu);
			M(Kafu_Kyu_Nendomatu);
			M(Ichijikin_Nendomatu);
			M(Rorei_Shinki2);
			M(Hiho_Kei);
			M(Hiho_Noufu);
			M(Fuka_Hiho);
			M(Hiho_Noufu_P);
			M(Fuka_Hiho_P);
			M(Hiho_Menjo);
			M(Hiho_Menjo_P);
			M(Rorei);
			M(Rorei_Kyu);
			M(Turo_Kyu);
			M(Gonen);
			M(Shogai_Ippan);
			M(Shogai_20mae);
			M(Shogai_Kyu);
			M(Izoku_Tuma);
			M(Izoku_Otto);
			M(Izoku_Ko);
			M(Kafu);
			M(Kafu_Kyu);
			M(Ichijikin);
#undef M
		}
		report_sizes();
		for (int i = 0; i < OUTFILE_NUM; i++)
			if (fp_out[i] != NULL) fclose(fp_out[i]);
		return 0;
	}

	if (stage == "stat") {
		/* `main.c` を丸ごと（`printout()` の手前まで）。
		 * 何年度まで回すかは SIML_YEARS（既定 3年）。
		 * `stat()` は集計して KISONENKIN と DOKUZI を書く。 */
		int years = 3;
		{ const char *e = getenv("SIML_YEARS");
		  if (e != NULL) years = atoi(e); }
		file_open(argv[2], fp_in, infile_name);
		file_open(argv[3], fp_out, outfile_name);
		seid();
		econ();
		waku();
		kaizen();
		noufuritu();
		int shub[4] = {2, 3, 5, 6};
		for (int i = 0; i < 4; i++) {
			dtst(shub[i]);
			kiso(shub[i]);
			shke(SUIKEISHONENDO, shub[i]);
			for (int nendo = SUIKEISHONENDO + 1;
			     nendo <= SUIKEISHONENDO + years; nendo++) {
				siml(nendo, shub[i]);
				shke(nendo, shub[i]);
			}
		}
		stat();
#define T(v) report_mem(#v, (const double *)&v, \
                        sizeof(v) / sizeof(double))
		T(Hiho_Kei);
		T(Hiho_Noufu);
		T(Fuka_Hiho);
		T(Hiho_Menjo);
		T(Rorei);
		T(Rorei_Kyu);
		T(Turo_Kyu);
		T(Gonen);
		T(Shogai_Ippan);
		T(Shogai_20mae);
		T(Shogai_Kyu);
		T(Izoku_Tuma);
		T(Izoku_Otto);
		T(Izoku_Ko);
		T(Kafu);
		T(Kafu_Kyu);
		T(Ichijikin);
#undef T
		report_sizes();
		for (int i = 0; i < OUTFILE_NUM; i++)
			if (fp_out[i] != NULL) fclose(fp_out[i]);
		return 0;
	}

	if (stage == "printout") {
		/* `main.c` を丸ごと（`printout()` まで）。SIML_YEARS（既定 3年）。
		 * `printout()` は年度末を年度間に上書きしてから5本書く。 */
		int years = 3;
		{ const char *e = getenv("SIML_YEARS");
		  if (e != NULL) years = atoi(e); }
		file_open(argv[2], fp_in, infile_name);
		file_open(argv[3], fp_out, outfile_name);
		seid();
		econ();
		waku();
		kaizen();
		noufuritu();
		int shub[4] = {2, 3, 5, 6};
		for (int i = 0; i < 4; i++) {
			dtst(shub[i]);
			kiso(shub[i]);
			shke(SUIKEISHONENDO, shub[i]);
			for (int nendo = SUIKEISHONENDO + 1;
			     nendo <= SUIKEISHONENDO + years; nendo++) {
				siml(nendo, shub[i]);
				shke(nendo, shub[i]);
			}
		}
		stat();
		printout();
#define P(v) report_mem(#v, (const double *)&v, \
                        sizeof(v) / sizeof(double))
		P(Rorei);
		P(Rorei_Kyu);
		P(Turo_Kyu);
		P(Gonen);
		P(Shogai_Ippan);
		P(Shogai_20mae);
		P(Shogai_Kyu);
		P(Izoku_Tuma);
		P(Izoku_Otto);
		P(Izoku_Ko);
		P(Kafu);
		P(Kafu_Kyu);
		P(Ichijikin);
#undef P
		report_sizes();
		for (int i = 0; i < OUTFILE_NUM; i++)
			if (fp_out[i] != NULL) fclose(fp_out[i]);
		return 0;
	}

	if (stage == "strop") {
		/* `str_op.c` の8つの型 × 最大8つの演算を、決めた入力で通す。
		 * 入力は「欄を 0.125 の倍数で順に埋めたもの」と、その3倍。
		 * 0.125 は2の冪なので丸めが入らず、演算の食い違いだけが出る。
		 * 改定率は 1.008 と 0.997（IEEE で近い数でない値）にする。 */
		double r1 = 1.008, r2 = 0.997;

		/* 欄を順に埋める（`double` だけで詰め物が無いので memcpy 相当
		 * の書き方ができる。上の sizeof の確かめが前提） */
#define FILL(v, mul) do { \
	double *p = (double *)&(v); \
	size_t n_ = sizeof(v) / sizeof(double); \
	for (size_t i_ = 0; i_ < n_; i_++) p[i_] = (mul) * 0.125 * (double)(i_ + 1); \
} while (0)

#define OPS_COMMON(T, nm) do { \
	struct T x, y, z, o; \
	FILL(x, 1.0); FILL(y, 3.0); FILL(z, 7.0); \
	o = add(x, y);        report_mem(nm "_add", (const double *)&o, \
	                                 sizeof(o) / sizeof(double)); \
} while (0)

#define OP_SCALAR(T, nm) do { \
	struct T x, o; FILL(x, 1.0); \
	o = scalar(2.25, x); report_mem(nm "_scalar", (const double *)&o, \
	                                sizeof(o) / sizeof(double)); \
} while (0)

#define OP_MUL(T, nm) do { \
	struct T x, y, o; FILL(x, 1.0); FILL(y, 3.0); \
	o = multiply(x, y); report_mem(nm "_multiply", (const double *)&o, \
	                               sizeof(o) / sizeof(double)); \
} while (0)

#define OP_NENDOKAN(T, nm) do { \
	struct T x, y, o; FILL(x, 1.0); FILL(y, 3.0); \
	o = nendokan(x, y, r1); report_mem(nm "_nendokan", \
	                                   (const double *)&o, \
	                                   sizeof(o) / sizeof(double)); \
} while (0)

#define OP_NENDOKAN2(T, nm) do { \
	struct T x, y, o; FILL(x, 1.0); FILL(y, 3.0); \
	o = nendokan(x, y, r1, r2); report_mem(nm "_nendokan", \
	                                       (const double *)&o, \
	                                       sizeof(o) / sizeof(double)); \
} while (0)

#define OP_NENDOKAN64(T, nm) do { \
	struct T x, y, z, o; FILL(x, 1.0); FILL(y, 3.0); FILL(z, 7.0); \
	o = nendokan_64(x, y, z, r1); report_mem(nm "_nendokan_64", \
	                                         (const double *)&o, \
	                                         sizeof(o) / sizeof(double)); \
} while (0)

#define OP_ADJUST(T, nm) do { \
	struct T x, o; FILL(x, 1.0); \
	o = adjustbenefit(0.9985, x); report_mem(nm "_adjustbenefit", \
	                                         (const double *)&o, \
	                                         sizeof(o) / sizeof(double)); \
} while (0)

		OPS_COMMON(hihokensha, "hihokensha");
		OP_SCALAR(hihokensha, "hihokensha");
		{
			struct hihokensha x, o;
			FILL(x, 1.0);
			o = average_by_ninzu(x);
			report_mem("hihokensha_average_by_ninzu",
			           (const double *)&o, sizeof(o) / sizeof(double));
			/* ninzu が 0 のときも見る */
			FILL(x, 1.0);
			x.ninzu = 0.0;
			o = average_by_ninzu(x);
			report_mem("hihokensha_average_by_ninzu_0",
			           (const double *)&o, sizeof(o) / sizeof(double));
			/* scalar_2 は特定期間の前後で3通り */
			int ns[3] = {TOKUTEI_NENDO - 1, TOKUTEI_NENDO,
			             TOKUTEI_NENDO + 1};
			for (int i = 0; i < 3; i++) {
				char nm[64];
				FILL(x, 1.0);
				o = scalar_2(2.25, x, ns[i]);
				snprintf(nm, sizeof nm, "hihokensha_scalar_2_%d", ns[i]);
				report_mem(nm, (const double *)&o,
				           sizeof(o) / sizeof(double));
			}
		}

		OPS_COMMON(rorei, "rorei");
		OP_SCALAR(rorei, "rorei");
		OP_MUL(rorei, "rorei");
		OP_NENDOKAN(rorei, "rorei");
		OP_NENDOKAN64(rorei, "rorei");
		OP_ADJUST(rorei, "rorei");

		OPS_COMMON(rorei_kyu, "rorei_kyu");
		OP_SCALAR(rorei_kyu, "rorei_kyu");
		OP_MUL(rorei_kyu, "rorei_kyu");
		OP_NENDOKAN(rorei_kyu, "rorei_kyu");
		OP_NENDOKAN64(rorei_kyu, "rorei_kyu");
		OP_ADJUST(rorei_kyu, "rorei_kyu");

		OPS_COMMON(gonen, "gonen");
		OP_SCALAR(gonen, "gonen");
		OP_NENDOKAN(gonen, "gonen");
		OP_NENDOKAN64(gonen, "gonen");
		OP_ADJUST(gonen, "gonen");

		OPS_COMMON(shogai, "shogai");
		OP_SCALAR(shogai, "shogai");
		OP_MUL(shogai, "shogai");
		OP_NENDOKAN2(shogai, "shogai");
		OP_NENDOKAN64(shogai, "shogai");
		OP_ADJUST(shogai, "shogai");

		OPS_COMMON(izoku, "izoku");
		OP_SCALAR(izoku, "izoku");
		OP_MUL(izoku, "izoku");
		OP_NENDOKAN2(izoku, "izoku");
		OP_NENDOKAN64(izoku, "izoku");
		OP_ADJUST(izoku, "izoku");

		OPS_COMMON(kafu, "kafu");
		OP_SCALAR(kafu, "kafu");
		OP_MUL(kafu, "kafu");
		OP_NENDOKAN(kafu, "kafu");
		OP_ADJUST(kafu, "kafu");

		OPS_COMMON(ichijikin, "ichijikin");
		OP_NENDOKAN(ichijikin, "ichijikin");
		OP_NENDOKAN64(ichijikin, "ichijikin");

		report_sizes();
		return 0;
	}

	fprintf(stderr, "unknown stage %s\n", stage.c_str());
	return 2;
}
