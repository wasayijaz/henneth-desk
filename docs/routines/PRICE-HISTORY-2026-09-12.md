# Price-history integrity investigation — 2026-09-12

Read-only evidence from the isolated checkout. No production state was refreshed or written.

## Friday replay

`post_close_integrity.evaluate(now=2026-09-11T23:59:00+05:00)` returned `fail`:

- `indices.json` capture is `2026-09-11 18:45` without an offset, so the gate correctly rejects it as ambiguous.
- The gate denominator is exact-universe PSX symbols with positive volume in `state/ohlc_daily/2026-09-11.json`; it does not join to `coverage.json`.
- 487 traded symbols; 451 have a same-day final history bar; 36 are missing (92.61%, below 99%).

The exact missing set is:

`AMTEXNC ARUJNC ASCNC BELANC DBCINC DSLNC DWAENC DWSMNC ESBLNC FCELNC FILNC FSWLNC GAMONNC GCWLPRS GSPMNC HASCOLNC HIRATNC HWQSNC IMLNC JUBSNC KSTMNC NCMLNC PASLNC PASMNC PECONC PILNC PPVCNC QUETNC RUBYNC SKRSNC SMLNC SPLNC SSMLNC SUHJNC TISL WAVESAPPR`

## Primary provider evidence

The authoritative ALLSHR page was fetched read-only: [https://dps.psx.com.pk/indices/ALLSHR](https://dps.psx.com.pk/indices/ALLSHR).

For HASCOL its raw row is:

```html
<td data-order="HASCOL"><a class="tbl__symbol" href="/company/HASCOL" data-title="Hascol Petroleum Limited" target="_blank"><strong>HASCOL</strong></a><div class="tag tag--skim tag--def">NC</div></td>
```

The declared security/issuer ticker is therefore the anchor `data-order`/`href` value `HASCOL`; `NC` is a separate badge. The current `_TAG_RE.sub("", cell)` parser removes that structure and concatenates the visible text to `HASCOLNC`, creating a synthetic ticker. This is a parser bug, not evidence that `HASCOLNC` is the provider's EOD identity.

The same structure was observed for the other affected `NC` rows: issuer anchor/base tickers are `AMTEX`, `ARUJ`, `ASC`, `BELA`, `DBCI`, `DSL`, `DWAE`, `DWSM`, `ESBL`, `FCEL`, `FIL`, `FSWL`, `GAMON`, `GSPM`, `HASCOL`, `HIRAT`, `HWQS`, `IML`, `JUBS`, `KSTM`, `NCML`, `PASL`, `PASM`, `PECO`, `PIL`, `PPVC`, `QUET`, `RUBY`, `SKRS`, `SML`, `SPL`, `SSML`, and `SUHJ`.

The exact-empty probe URLs were `https://dps.psx.com.pk/timeseries/eod/AMTEXNC`, `https://dps.psx.com.pk/timeseries/eod/ARUJNC`, `https://dps.psx.com.pk/timeseries/eod/ASCNC`, `https://dps.psx.com.pk/timeseries/eod/BELANC`, `https://dps.psx.com.pk/timeseries/eod/DBCINC`, `https://dps.psx.com.pk/timeseries/eod/DSLNC`, `https://dps.psx.com.pk/timeseries/eod/DWAENC`, `https://dps.psx.com.pk/timeseries/eod/DWSMNC`, `https://dps.psx.com.pk/timeseries/eod/ESBLNC`, `https://dps.psx.com.pk/timeseries/eod/FCELNC`, `https://dps.psx.com.pk/timeseries/eod/FILNC`, `https://dps.psx.com.pk/timeseries/eod/FSWLNC`, `https://dps.psx.com.pk/timeseries/eod/GAMONNC`, `https://dps.psx.com.pk/timeseries/eod/GSPMNC`, `https://dps.psx.com.pk/timeseries/eod/HASCOLNC`, `https://dps.psx.com.pk/timeseries/eod/HIRATNC`, `https://dps.psx.com.pk/timeseries/eod/HWQSNC`, `https://dps.psx.com.pk/timeseries/eod/IMLNC`, `https://dps.psx.com.pk/timeseries/eod/JUBSNC`, `https://dps.psx.com.pk/timeseries/eod/KSTMNC`, `https://dps.psx.com.pk/timeseries/eod/NCMLNC`, `https://dps.psx.com.pk/timeseries/eod/PASLNC`, `https://dps.psx.com.pk/timeseries/eod/PASMNC`, `https://dps.psx.com.pk/timeseries/eod/PECONC`, `https://dps.psx.com.pk/timeseries/eod/PILNC`, `https://dps.psx.com.pk/timeseries/eod/PPVCNC`, `https://dps.psx.com.pk/timeseries/eod/QUETNC`, `https://dps.psx.com.pk/timeseries/eod/RUBYNC`, `https://dps.psx.com.pk/timeseries/eod/SKRSNC`, `https://dps.psx.com.pk/timeseries/eod/SMLNC`, `https://dps.psx.com.pk/timeseries/eod/SPLNC`, `https://dps.psx.com.pk/timeseries/eod/SSMLNC`, and `https://dps.psx.com.pk/timeseries/eod/SUHJNC`; all returned HTTP 200 with zero rows.

The corresponding unsuffixed probe URLs were `https://dps.psx.com.pk/timeseries/eod/AMTEX`, `https://dps.psx.com.pk/timeseries/eod/ARUJ`, `https://dps.psx.com.pk/timeseries/eod/ASC`, `https://dps.psx.com.pk/timeseries/eod/BELA`, `https://dps.psx.com.pk/timeseries/eod/DBCI`, `https://dps.psx.com.pk/timeseries/eod/DSL`, `https://dps.psx.com.pk/timeseries/eod/DWAE`, `https://dps.psx.com.pk/timeseries/eod/DWSM`, `https://dps.psx.com.pk/timeseries/eod/ESBL`, `https://dps.psx.com.pk/timeseries/eod/FCEL`, `https://dps.psx.com.pk/timeseries/eod/FIL`, `https://dps.psx.com.pk/timeseries/eod/FSWL`, `https://dps.psx.com.pk/timeseries/eod/GAMON`, `https://dps.psx.com.pk/timeseries/eod/GSPM`, `https://dps.psx.com.pk/timeseries/eod/HASCOL`, `https://dps.psx.com.pk/timeseries/eod/HIRAT`, `https://dps.psx.com.pk/timeseries/eod/HWQS`, `https://dps.psx.com.pk/timeseries/eod/IML`, `https://dps.psx.com.pk/timeseries/eod/JUBS`, `https://dps.psx.com.pk/timeseries/eod/KSTM`, `https://dps.psx.com.pk/timeseries/eod/NCML`, `https://dps.psx.com.pk/timeseries/eod/PASL`, `https://dps.psx.com.pk/timeseries/eod/PASM`, `https://dps.psx.com.pk/timeseries/eod/PECO`, `https://dps.psx.com.pk/timeseries/eod/PIL`, `https://dps.psx.com.pk/timeseries/eod/PPVC`, `https://dps.psx.com.pk/timeseries/eod/QUET`, `https://dps.psx.com.pk/timeseries/eod/RUBY`, `https://dps.psx.com.pk/timeseries/eod/SKRS`, `https://dps.psx.com.pk/timeseries/eod/SML`, `https://dps.psx.com.pk/timeseries/eod/SPL`, `https://dps.psx.com.pk/timeseries/eod/SSML`, and `https://dps.psx.com.pk/timeseries/eod/SUHJ`. Every one returned HTTP 200, a same-day `2026-09-11` row, and positive history; the observed row counts were:

`AMTEX 567, ARUJ 782, ASC 1240, BELA 657, DBCI 567, DSL 1240, DWAE 567, DWSM 1123, ESBL 1177, FCEL 485, FIL 392, FSWL 382, GAMON 1001, GSPM 563, HASCOL 1240, HIRAT 1183, HWQS 836, IML 878, JUBS 989, KSTM 557, NCML 1028, PASL 1240, PASM 565, PECO 795, PIL 1208, PPVC 763, QUET 897, RUBY 891, SKRS 1197, SML 784, SPL 1215, SSML 1100, SUHJ 480`.

For all 33, the unsuffixed EOD row's `2026-09-11` volume matched the raw ALLSHR/market-watch row. Close matched for 31/33; `PASLNC` differed by Rs0.01 (EOD 2.52 vs market-watch 2.53) and `PASMNC` by Rs0.01 (EOD 8.36 vs market-watch 8.37). These minor close differences do not prove identity equivalence; the HTML anchor/badge structure is the primary identity evidence.

The other three missing exact URLs were `https://dps.psx.com.pk/timeseries/eod/GCWLPRS`, `https://dps.psx.com.pk/timeseries/eod/TISL`, and `https://dps.psx.com.pk/timeseries/eod/WAVESAPPR`; they returned 14, 14, and 10 EOD rows respectively, including `2026-09-11`. They are not `NC` badges, and their short series falls below the current listed ingestion floor of 20 despite positive same-day market-watch volume.

## Bounded implementation checkpoint

Do not add a blanket `NC` alias or strip suffixes. The next implementation should preserve the actual preferred ticker from the structured anchor/data field and store the badge separately (for example, `board_status: "NC"`) while retaining issuer/name metadata. It must define collision behavior before changing stored universe keys, history filenames, or downstream joins; `NC` badge status alone must not be treated as proof of security identity.

Lowering the listed 20-bar ingestion floor would only allow the three shallow records to be cached. It would not make them broadly research-eligible: `quant.py` requires 60 bars, `predictability.py` 150 bars, and liquidity measurement 30 bars; the research liquidity gate defaults to 500 bars. This is a separate eligibility decision, not a reason to distort the price-integrity denominator.

Owner checkpoint required before implementation because the prior assumption that `…NC` entries were independent non-company counters is materially false for these ALLSHR rows. No alias implementation is included here.
