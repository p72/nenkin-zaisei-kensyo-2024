/* ②厚生年金給付費推計のグローバル配列を原本から取り出すハーネス
 * ==============================================================
 * 原本の .cpp を**無修正でコンパイルしてリンク**し、`main.cpp` の代わりに
 * この `main()` を使う。段階（`cntl` → `fopn` → `flck` → `waku` → …）を
 * 引数で指定して、そこまで通したあとのグローバル配列を CRC32 で出す。
 *
 *   ./h <stage> [<array> ...]
 *
 *     stage  cntl / waku / econ / seid / krgn / kiso / dtst / shke /
 *            siml / siml2 / out / full
 *     array  省略すると段階ごとの既定の一覧
 *
 * `full` は `sepsd()` を丸ごと（KIJUN〜KE の 105 年度）通す。配列は
 * 出さず、出力ファイルを突き合わせるために使う。段階名の末尾に
 * `:1` `:4` `:5` を付けると制度を変えられる（既定は厚生年金 0）。
 *
 * 出力は1行1配列で（原本の `cout` の文言と混ざらないよう `## ` を付ける）
 *
 *     ## <名前> <要素数> <CRC32(16進)> <先頭の非ゼロ要素の %a>
 *
 * CRC32 は **C の行優先（row-major）**で 8 バイトずつ食わせる。NumPy の
 * `arr.tobytes()` と同じ並びになるので、Python 側と突き合わせられる。
 *
 * `main.cpp` が読む4つ（key, iname, iecon, iwname）と `cntl()` が読む
 * 残りは、原本と同じ順で標準入力から取る。
 */
#define SEPS_GLOBAL
#include "sepscommon.h"
#include "sepslib.h"
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>
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

/* ---- 各次元を行優先でたどる ---- */
static void walk(Crc &h, const v1_t &v) {
	for (size_t i = 0; i < v.size(); i++) h.add(v[i]);
}
static void walk(Crc &h, const v2_t &v) {
	for (size_t i = 0; i < v.size(); i++) walk(h, v[i]);
}
static void walk(Crc &h, const v3_t &v) {
	for (size_t i = 0; i < v.size(); i++) walk(h, v[i]);
}
static void walk(Crc &h, const v4_t &v) {
	for (size_t i = 0; i < v.size(); i++) walk(h, v[i]);
}
static void walk(Crc &h, const v5_t &v) {
	for (size_t i = 0; i < v.size(); i++) walk(h, v[i]);
}

template <typename T>
static void report(const char *name, const T &v) {
	Crc h;
	walk(h, v);
	printf("## %s %lld %08x", name, h.n, h.value());
	if (h.have_first) printf(" %a\n", h.first);
	else printf(" -\n");
}

/* 段階の中で何回も呼ぶところ用に `s1_q` のような名前を作る。
 * `report` はその場で printf するので、1つの緩衝で足りる。 */
static char nmbuf[64];
static const char *nm(const char *pfx, const char *name) {
	snprintf(nmbuf, sizeof nmbuf, "%s%s", pfx, name);
	return nmbuf;
}

/* スカラーの設定値も出す */
static void report_int(const char *name, int v) {
	printf("## %s int %d -\n", name, v);
}
static void report_dbl(const char *name, double v) {
	printf("## %s dbl %a -\n", name, v);
}

int main(int argc, char *argv[]) {
	if (argc < 2) { fprintf(stderr, "usage: %s <stage>\n", argv[0]); return 2; }
	string stage = argv[1];

	cin >> key;
	cin >> iname;
	cin >> iecon;
	cin >> iwname;

	seidver = 1;
	seps::zero_init();
	seps::cntl();

	if (stage == "cntl") {
		report_int("key", key);
		report_int("iname", iname);
		report_int("iecon", iecon);
		report_int("iwname", iwname);
		report_int("seidver", seidver);
		report_int("psly", psly);
		report_int("pslsi", pslsi);
		report_int("pslsi2", pslsi2);
		report_int("seimei", seimei);
		report_int("seiy", seiy);
		report_int("kzn", kzn);
		report_int("flg_part", flg_part);
		report_int("partyr1", partyr1);
		report_int("partyr2", partyr2);
		report_int("partyr3", partyr3);
		report_int("partyr4", partyr4);
		report_int("flg_sigo", flg_sigo);
		report_int("canyr", canyr);
		report_int("flg_kozax", flg_kozax);
		report_int("kozaxyr", kozaxyr);
		report_int("kozax", kozax);
		report_int("houjou", houjou);
		report_int("houjouyr", houjouyr);
		report_dbl("houjour1", houjour1);
		report_dbl("houjour2", houjour2);
		report_int("flg_inout", flg_inout);
		report_int("flg_hantei", flg_hantei);
		report_int("flg_okure", flg_okure);
		report_int("flg_kurisage", flg_kurisage);
		report_int("flg_tuuroutest", flg_tuuroutest);
		report_int("flg_hsr", flg_hsr);
		report_int("hsr_endy", hsr_endy);
		report_dbl("hsr_r", hsr_r);
		report_int("flg_siktuika", flg_siktuika);
		report_int("flg_toukei", flg_toukei);
		report_int("flg_gtest", flg_gtest);
		report_int("flg_bzwtest", flg_bzwtest);
		report_int("chinsura", chinsura);
		report_int("kaite", kaite);
		report_int("nenbeex", nenbeex);
		report_int("xb", xb);
		report_int("xa", xa);
		report_int("cht_flg", cht_flg);
		report_dbl("hikrate", hikrate);
		report_int("flg_hiho70", flg_hiho70);
		report_int("hiho70yr", hiho70yr);
		report_int("flg_kaisho", flg_kaisho);
		report_int("flg_sankyu", flg_sankyu);
		report_int("nenbe65", nenbe65);
		report("kflcan", kflcan);
		report("partbbn", partbbn);
		report("partbbn2", partbbn2);
		report("tz", tz);
		report("kfprx", kfprx);
		report("apdmy", apdmy);
		report("atdmy", atdmy);
		return 0;
	}

	/* ここから先は制度ごと。既定は厚生年金（pseid = 0）。
	 * 段階名の末尾に `:1` `:4` `:5` を付けると共済を見る
	 * （`out:1` なら国家公務員共済）。`main.cpp` は 2 と 3 を飛ばす。 */
	pseid = 0;
	{
		size_t c = stage.find(':');
		if (c != string::npos) {
			pseid = atoi(stage.c_str() + c + 1);
			stage = stage.substr(0, c);
			if (pseid != 1 && pseid != 4 && pseid != 5) {
				fprintf(stderr, "pseid %d は main.cpp が飛ばす\n", pseid);
				return 2;
			}
		}
	}
	konen = (pseid == 0) ? 1 : 0;
	seps::zero_sepsd();

	if (stage == "full") {
		/* `main.cpp` が1制度ぶんに対してするのと同じこと。
		 * `sepsd()` が自分で `fopn()` と `fcls()` を呼ぶので、
		 * ここでは開かない。出力を丸ごと突き合わせるための段階。 */
		seps::sepsd();
		return 0;
	}

	seps::fopn();
	seps::flck();

	if (stage == "waku") {
		seps::waku();
		report("pop", pop);
		report("l", l);
		report("lpt", lpt);
		report("lpt1", lpt1);
		report("lpt2", lpt2);
		report("lpt3", lpt3);
		report("lpt4", lpt4);
		report_int("s", s);
		report_int("k", k);
		seps::fcls();
		return 0;
	}

	seps::waku();
	seps::econ();

	if (stage == "econ") {
		report("ri", ri);
		report("h", h);
		report("ci0", ci0);
		report("dir", dir);
		report("jz_shk", jz_shk);
		report("hh", hh);
		report("ci", ci);
		report("hdum", hdum);
		report("ci2", ci2);
		report("hp2", hp2);
		report("ad", ad);
		report("ad2", ad2);
		report("bd", bd);
		report("chwd", chwd);
		report("qp", qp);
		report_dbl("hh2_1999", hh2_1999);
		report_dbl("hh2_2000", hh2_2000);
		report_dbl("hh2_2001", hh2_2001);
		seps::fcls();
		return 0;
	}

	seps::seid();

	if (stage == "seid") {
		report("pre", pre);
		report("pres", pres);
		report("flt", flt);
		report("adt", adt);
		report("sadt", sadt);
		report("cadt", cadt);
		report("wife", wife);
		report("can", can);
		report("can2", can2);
		report("ha", ha);
		report("hb", hb);
		report("ema", ema);
		report("emb", emb);
		report("emc", emc);
		report("ee", ee);
		report("rs", rs);
		report("sik", sik);
		report("sikr", sikr);
		report("nos", nos);
		report("routsu", routsu);
		report("qp", qp);
		report("br", br);
		report("bn", bn);
		report("bnpt", bnpt);
		report("dmpt2", dmpt2);
		report("partbbn", partbbn);
		report_dbl("pra", pra);
		report_dbl("prb", prb);
		report_dbl("pras", pras);
		report_dbl("prbs", prbs);
		report_dbl("fl", fl);
		report_dbl("fl1", fl1);
		report_dbl("minb", minb);
		report_dbl("wif", wif);
		report_dbl("senll", senll);
		report_dbl("srv", srv);
		seps::fcls();
		return 0;
	}

	seps::krgn();

	if (stage == "krgn") {
		report("riss", riss);
		report("rigd", rigd);
		report("rigk", rigk);
		report("rigbe", rigbe);
		seps::fcls();
		return 0;
	}

	if (stage == "siml" || stage == "siml2") {
		/* `sepsd.cpp` と同じ順で kiso → dtst → shke、そのあと
		 * k = KIJUN+1（siml2 なら KIJUN+2 まで）で siml → shke。 */
		int kmax = (stage == "siml") ? KIJUN + 1 : KIJUN + 2;
		GLOBAL_FOR(s, 1, 3) {
			if (pseid != 0 && s >= 3) break;
			s2 = s;
			seps::kiso();
			k = KIJUN;
			xend = (pseid == 0) ? 90 : 75;
			tend = xend - 15;
			seps::dtst();
			seps::shke();
			GLOBAL_FOR(k, KIJUN + 1, kmax) {
				seps::siml();
				seps::shke();
			}
			char p[32];
			snprintf(p, sizeof p, "s%d_", s);
			report(nm(p, "g"), g);
			report(nm(p, "ge"), ge);
			report(nm(p, "gpt"), gpt);
			report(nm(p, "gz"), gz);
			report(nm(p, "gn"), gn);
			report(nm(p, "gez"), gez);
			report(nm(p, "gnn"), gnn);
			report(nm(p, "ye"), ye);
			report(nm(p, "y"), y);
			report(nm(p, "ypt"), ypt);
			report(nm(p, "q2"), q2);
			report(nm(p, "bb"), bb);
			report(nm(p, "bbnp"), bbnp);
			report(nm(p, "bbpt"), bbpt);
			report(nm(p, "z"), z);
			report(nm(p, "ze"), ze);
			report(nm(p, "w"), w);
			report(nm(p, "we"), we);
			report(nm(p, "chwd"), chwd);
			report(nm(p, "gd"), gd);
			report(nm(p, "r"), r);
			report(nm(p, "rn"), rn);
			report(nm(p, "hn"), hn);
			report(nm(p, "hnn"), hnn);
			report(nm(p, "f"), f);
			report(nm(p, "fn"), fn);
			report(nm(p, "f_hik"), f_hik);
			report(nm(p, "f_min"), f_min);
			report(nm(p, "fnhik"), fnhik);
			report(nm(p, "fnmin"), fnmin);
			report(nm(p, "pshn"), pshn);
			report(nm(p, "rsen"), rsen);
			report(nm(p, "fsen"), fsen);
			report(nm(p, "fsenhik"), fsenhik);
			report(nm(p, "fsenmin"), fsenmin);
			report(nm(p, "rsenn"), rsenn);
			report(nm(p, "fsenn"), fsenn);
			report(nm(p, "hnsen"), hnsen);
			report(nm(p, "rhantei"), rhantei);
			report(nm(p, "fhantei"), fhantei);
			report(nm(p, "fpart"), fpart);
			report(nm(p, "t4"), t4);
			report(nm(p, "t6"), t6);
			report(nm(p, "d3"), d3);
			report(nm(p, "d3x"), d3x);
			report(nm(p, "okisor"), okisor);
			report(nm(p, "l"), l);
			report(nm(p, "lpt"), lpt);
			report_int(nm(p, "it"), it);
			report_int(nm(p, "xr"), xr);
			report_int(nm(p, "xxr"), xxr);
			report_int(nm(p, "xrb"), xrb);
			report_dbl(nm(p, "tn"), tn);
			report_dbl(nm(p, "ta"), ta);
			report_dbl(nm(p, "srv"), srv);
			report_dbl(nm(p, "pslr"), pslr);
		}
		seps::fcls();
		return 0;
	}

	if (stage == "out") {
		/* `sepsd.cpp` の尾（outkn → rousaki → pstat → stat → crshfl →
		 * outhou）を、siml を2年だけ回したあとで通す。年度の範囲は
		 * 原本のまま（KIJUN〜KE）なので、回していない年度は 0 のまま
		 * 平均や「計」に入る。C 版と移植版で同じ入り方をするので
		 * 突き合わせには使える。 */
		GLOBAL_FOR(s, 1, 3) {
			if (pseid != 0 && s >= 3) break;
			s2 = s;
			seps::kiso();
			k = KIJUN;
			xend = (pseid == 0) ? 90 : 75;
			tend = xend - 15;
			seps::dtst();
			seps::shke();
			GLOBAL_FOR(k, KIJUN + 1, KIJUN + 2) {
				seps::siml();
				seps::shke();
			}
		}
		if (key == 11 || key == 12 || key == 13) seps::outkn();
		if (flg_toukei == 0) seps::rousaki();
		if (key == 11 || key == 13) seps::pstat();
		seps::stat();
		seps::crshfl();
		if (key == 11) seps::outhou();

		report("d3", d3);
		report("d3x", d3x);
		report("d3xs", d3xs);
		report("kfprx", kfprx);
		report("a", a);
		report("aal", aal);
		report("aiku", aiku);
		report("ap", ap);
		report("appart", appart);
		report("at", at);
		report("a60", a60);
		report("a65", a65);
		report("a70", a70);
		report("a75", a75);
		report("a85", a85);
		report("ap65", ap65);
		report("ap70", ap70);
		report("ap75", ap75);
		report("ap85", ap85);
		report("appart65", appart65);
		report("appart70", appart70);
		report("appart75", appart75);
		report("appart85", appart85);
		report("apart", apart);
		report("aikupart", aikupart);
		report("a60part", a60part);
		report("a65part", a65part);
		report("a70part", a70part);
		report("a75part", a75part);
		report("a85part", a85part);
		report("gee", gee);
		report("geept", geept);
		seps::fcls();
		return 0;
	}

	if (stage == "shke") {
		/* `sepsd.cpp` と同じ順で kiso → dtst → shke を種別ごとに1回 */
		GLOBAL_FOR(s, 1, 3) {
			if (pseid != 0 && s >= 3) break;
			s2 = s;
			seps::kiso();
			k = KIJUN;
			xend = (pseid == 0) ? 90 : 75;
			tend = xend - 15;
			seps::dtst();
			seps::shke();
			char p[32];
			snprintf(p, sizeof p, "s%d_", s);
			report(nm(p, "t4"), t4);
			report(nm(p, "t4k"), t4k);
			report(nm(p, "t6"), t6);
			report(nm(p, "t6k"), t6k);
			report(nm(p, "hn2"), hn2);
			report(nm(p, "hn2k"), hn2k);
			report(nm(p, "gee"), gee);
			report(nm(p, "geept"), geept);
			report(nm(p, "ap"), ap);
			report(nm(p, "apdum"), apdum);
			report(nm(p, "ap65"), ap65);
			report(nm(p, "ap70"), ap70);
			report(nm(p, "ap75"), ap75);
			report(nm(p, "ap85"), ap85);
			report(nm(p, "appart"), appart);
			report(nm(p, "a"), a);
			report(nm(p, "adum"), adum);
			report(nm(p, "aiku"), aiku);
			report(nm(p, "a60"), a60);
			report(nm(p, "a65"), a65);
			report(nm(p, "a70"), a70);
			report(nm(p, "a75"), a75);
			report(nm(p, "a85"), a85);
			report(nm(p, "apart"), apart);
			report(nm(p, "ax"), ax);
			report(nm(p, "gx"), gx);
			report(nm(p, "gtal"), gtal);
			report(nm(p, "getal"), getal);
			report(nm(p, "g2"), g2);
			report(nm(p, "bb2"), bb2);
			report(nm(p, "z2"), z2);
			report(nm(p, "w2"), w2);
			report(nm(p, "g3"), g3);
			report(nm(p, "bb3"), bb3);
			report(nm(p, "okisor"), okisor);
			report(nm(p, "okiso2x"), okiso2x);
			report(nm(p, "dk3x"), dk3x);
			report(nm(p, "d3"), d3);
			report(nm(p, "d3x"), d3x);
			report(nm(p, "d3xs"), d3xs);
			report_int(nm(p, "xxr"), xxr);
			report_int(nm(p, "xrb"), xrb);
		}
		seps::fcls();
		return 0;
	}

	if (stage == "dtst") {
		/* `sepsd.cpp` と同じ順で kiso → dtst を種別ごとに回す */
		GLOBAL_FOR(s, 1, 3) {
			if (pseid != 0 && s >= 3) break;
			s2 = s;
			seps::kiso();
			k = KIJUN;
			xend = (pseid == 0) ? 90 : 75;
			tend = xend - 15;
			seps::dtst();
			char p[32];
			snprintf(p, sizeof p, "s%d_", s);
			report(nm(p, "g"), g);
			report(nm(p, "ge"), ge);
			report(nm(p, "gpt"), gpt);
			report(nm(p, "bb"), bb);
			report(nm(p, "bbpt"), bbpt);
			report(nm(p, "z"), z);
			report(nm(p, "ze"), ze);
			report(nm(p, "w"), w);
			report(nm(p, "we"), we);
			report(nm(p, "psz"), psz);
			report(nm(p, "psze"), psze);
			report(nm(p, "gd"), gd);
			report(nm(p, "r"), r);
			report(nm(p, "f"), f);
			report(nm(p, "f_min"), f_min);
			report(nm(p, "f_hik"), f_hik);
			report(nm(p, "hn"), hn);
			report(nm(p, "pshn"), pshn);
			report(nm(p, "rsen"), rsen);
			report(nm(p, "hnsen"), hnsen);
			report(nm(p, "pshnsen"), pshnsen);
			report(nm(p, "fsen"), fsen);
			report(nm(p, "fsenmin"), fsenmin);
			report(nm(p, "fsenhik"), fsenhik);
			report(nm(p, "fkouzai2"), fkouzai2);
			report_int(nm(p, "xxr"), xxr);
			report_int(nm(p, "xrb"), xrb);
		}
		seps::fcls();
		return 0;
	}

	if (stage == "kiso") {
		/* `sepsd.cpp` の種別ループと同じ形で `kiso()` だけを回す。
		 * `kisor` ファイルは1回の呼び出しで1節ずつ進むので、
		 * s = 1, 2, 3 と3回呼ぶ必要がある。s ごとに配列を出す。 */
		GLOBAL_FOR(s, 1, 3) {
			if (pseid != 0 && s >= 3) break;
			s2 = s;
			seps::kiso();
			char p[32];
			snprintf(p, sizeof p, "s%d_", s);
			report(nm(p, "q"), q);
			report(nm(p, "u"), u);
			report(nm(p, "rt"), rt);
			report(nm(p, "yx"), yx);
			report(nm(p, "ns"), ns);
			report(nm(p, "rc"), rc);
			report(nm(p, "cl"), cl);
			report(nm(p, "cl2"), cl2);
			report(nm(p, "kd"), kd);
			report(nm(p, "ikucoe"), ikucoe);
			report(nm(p, "jiiku"), jiiku);
			report_int(nm(p, "xxr"), xxr);
			report_int(nm(p, "xrb"), xrb);
		}
		seps::fcls();
		return 0;
	}

	fprintf(stderr, "unknown stage %s\n", stage.c_str());
	seps::fcls();
	return 2;
}
