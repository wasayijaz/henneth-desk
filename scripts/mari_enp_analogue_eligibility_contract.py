"""Fail-closed MARI offshore E&P analogue eligibility contract."""
from __future__ import annotations
from datetime import date
import hashlib, json, math, re
from typing import Any, Mapping

CONTRACT_VERSION = "mari_enp_analogue_eligibility_v1"
HORIZONS = ("1Q", "2Q", "4Q", "8Q")
MIN_SAMPLE = 3
CASE_ID = "case_mari_offshore_exploration_blocks_observed_v1"
TARGET_EVENT_ID = "evt_3d1dae7553f73da60ba3"
TARGET_SOURCE_EVENT_ID = "evt_ddf99590afb6dacddbde"
CANDIDATE_EVENT_ID = "evt_b25decfc180474cbe066"
TARGET_SOURCE_ID = "psx:265594"
CANDIDATE_SOURCE_ID = "psx:260446"
TARGET_DATE = "2025-11-13"
CANDIDATE_DATE = "2025-09-30"
TARGET_URL = "https://dps.psx.com.pk/download/document/265594.pdf"
CANDIDATE_URL = "https://dps.psx.com.pk/download/document/260446.pdf"
TARGET_HASH = "cdc3f69157f5e5803238ba347ecb4e96f7297479df87d345739896913de8aae4"
TARGET_EVIDENCE_HASH = "56c298f041bd756cd184e75d122f5a95cc6879f4b5fa037786007948b76d3d83"
CANDIDATE_HASH = "c13ccb4de58ad005bca106942721490593fe219ff45906c68280ea7856192e42"
CANDIDATE_EVIDENCE_HASH = "dd83c62cb781e2a57f5ae595a7184ea786a3e5890f7f7cc96cd93e23f958a177"

ROOT_KEYS = {"contract_version","mode","cutoff","target_event","candidate_observations","observed_candidate_count","retained_candidate_note"}
EVENT_KEYS = {"event_id","case_id","symbol","event_type","event_subtype","effective_date","mechanism","scale","operator_status","working_interest_pct","source"}
SOURCE_KEYS = {"id","event_id","url","page","content_sha256","evidence_sha256","date","cutoff"}
CAND_KEYS = EVENT_KEYS | {"candidate_id","horizon","endpoint_date","endpoint_available_on","endpoint_status","outcome_return_pct"}
BANNED = ("you should","buy","sell","accumulate","target price","price target","causal","forecast","valuation","recommendation")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

REAL_TARGET = {"event_id":TARGET_EVENT_ID,"case_id":CASE_ID,"symbol":"MARI","event_type":"acquisition_divestment","event_subtype":"acquisition","effective_date":TARGET_DATE,"mechanism":"offshore_exploration_block_acquisition","scale":"offshore_exploration_blocks","operator_status":None,"working_interest_pct":None,"source":{"id":TARGET_SOURCE_ID,"event_id":TARGET_SOURCE_EVENT_ID,"url":TARGET_URL,"page":3,"content_sha256":TARGET_HASH,"evidence_sha256":TARGET_EVIDENCE_HASH,"date":TARGET_DATE,"cutoff":TARGET_DATE}}
REAL_CANDIDATE = {"candidate_id":"mari_peshawar_working_interest_observed_v1","event_id":CANDIDATE_EVENT_ID,"case_id":None,"symbol":"MARI","event_type":"acquisition_divestment","event_subtype":"acquisition","effective_date":CANDIDATE_DATE,"mechanism":"working_interest_acquisition","scale":"peshawar_onshore_block","operator_status":"operator","working_interest_pct":None,"source":{"id":CANDIDATE_SOURCE_ID,"event_id":"evt_b25decfc180474cbe066","url":CANDIDATE_URL,"page":1,"content_sha256":CANDIDATE_HASH,"evidence_sha256":CANDIDATE_EVIDENCE_HASH,"date":CANDIDATE_DATE,"cutoff":CANDIDATE_DATE}}

def _day(v: Any):
    try: return date.fromisoformat(v) if isinstance(v,str) else None
    except ValueError: return None

def _finite(v: Any): return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v))
def _text(v: Any): return isinstance(v,str) and bool(v.strip()) and v.strip().casefold() not in {"unknown","tbd","n/a","none","null"}
def _closed(m: Mapping[str,Any], keys:set[str], p:str, out:list[str]):
    for k in m: 
        if k not in keys: out.append(f"{p}.{k}: unknown field")
def _walk_text(v: Any):
    if isinstance(v,str): return v.casefold()
    if isinstance(v,Mapping): return " ".join(_walk_text(x) for x in v.values())
    if isinstance(v,list): return " ".join(_walk_text(x) for x in v)
    return ""
def _source_errors(s: Any, mode:str, cutoff:date|None, p:str):
    e=[]
    if not isinstance(s,Mapping): return [f"{p}: must be a mapping"]
    _closed(s,SOURCE_KEYS,p,e)
    if not _text(s.get("id")): e.append(f"{p}.id: required")
    if not _text(s.get("event_id")): e.append(f"{p}.event_id: required")
    if not isinstance(s.get("url"),str) or not s["url"].startswith("https://"): e.append(f"{p}.url: required https URL")
    if not isinstance(s.get("page"),int) or isinstance(s.get("page"),bool) or s["page"]<1: e.append(f"{p}.page: positive integer required")
    for k in ("content_sha256","evidence_sha256"):
        if s.get(k) is not None and (not isinstance(s[k],str) or not HEX64.fullmatch(s[k])): e.append(f"{p}.{k}: must be sha256 or null")
    for k in ("date","cutoff"):
        if _day(s.get(k)) is None: e.append(f"{p}.{k}: must be YYYY-MM-DD")
    if _day(s.get("date")) and _day(s.get("cutoff")) and _day(s["date"])>_day(s["cutoff"]): e.append(f"{p}: date after cutoff")
    if cutoff and _day(s.get("cutoff")) and _day(s["cutoff"])>cutoff: e.append(f"{p}.cutoff: after product cutoff")
    if mode=="fixture" and not s.get("id","").startswith("fixture:"): e.append(f"{p}.id: fixture source required")
    if mode=="real" and s.get("id","").startswith("fixture:"): e.append(f"{p}.id: real mode rejects fixture source")
    return e

def validate_payload(payload: Mapping[str,Any]) -> list[str]:
    e=[]
    if not isinstance(payload,Mapping): return ["payload: must be a mapping"]
    _closed(payload,ROOT_KEYS,"payload",e)
    if payload.get("contract_version")!=CONTRACT_VERSION: e.append("contract_version: mismatch")
    mode=payload.get("mode")
    if mode not in ("real","fixture"): e.append("mode: must be real or fixture")
    cutoff=_day(payload.get("cutoff"))
    if cutoff is None: e.append("cutoff: must be YYYY-MM-DD")
    target=payload.get("target_event")
    if not isinstance(target,Mapping): e.append("target_event: must be a mapping"); target={}
    else:
        _closed(target,EVENT_KEYS,"target_event",e)
        for k in ("event_id","case_id","symbol","event_type","event_subtype","mechanism","scale"):
            if not _text(target.get(k)): e.append(f"target_event.{k}: required")
        if target.get("symbol")!="MARI" or target.get("case_id")!=CASE_ID: e.append("target_event: MARI offshore case identity mismatch")
        td=_day(target.get("effective_date"));
        if td is None: e.append("target_event.effective_date: invalid date")
        elif cutoff and td>cutoff: e.append("target_event.effective_date: after cutoff")
        if target.get("operator_status") is not None and not _text(target.get("operator_status")): e.append("target_event.operator_status: null or nonempty text")
        if target.get("working_interest_pct") is not None and not _finite(target.get("working_interest_pct")): e.append("target_event.working_interest_pct: finite number or null")
        e += _source_errors(target.get("source"),str(mode),cutoff,"target_event.source")
        if isinstance(target.get("source"), Mapping) and target.get("source", {}).get("event_id") not in (target.get("event_id"), TARGET_SOURCE_EVENT_ID):
            e.append("target_event.source.event_id: must bind owning target event")
        if mode=="real":
            for k,v in REAL_TARGET.items():
                if k=="source": continue
                if target.get(k)!=v: e.append(f"target_event.{k}: does not match canonical retained offshore target")
            src=target.get("source") or {}
            for k,v in REAL_TARGET["source"].items():
                if src.get(k)!=v: e.append(f"target_event.source.{k}: does not match canonical retained source")
    candidates=payload.get("candidate_observations")
    if not isinstance(candidates,list): e.append("candidate_observations: must be a list"); candidates=[]
    if not isinstance(payload.get("observed_candidate_count"),int) or isinstance(payload.get("observed_candidate_count"),bool): e.append("observed_candidate_count: integer required")
    elif payload.get("observed_candidate_count") != len(candidates): e.append("observed_candidate_count: must equal observed candidate rows")
    if mode == "real" and payload.get("observed_candidate_count") != 1: e.append("observed_candidate_count: canonical retained count is 1")
    if not _text(payload.get("retained_candidate_note")): e.append("retained_candidate_note: required")
    td=_day(target.get("effective_date"))
    if mode == "fixture":
        ts = target.get("source") if isinstance(target.get("source"), Mapping) else {}
        if target.get("event_id") != TARGET_EVENT_ID or ts.get("id") != "fixture:target-0": e.append("fixture target: exact sealed identity required")
        if len(candidates) != 3: e.append("fixture candidates: exact sealed set requires three rows")
    seen=set(); seen_ids=set(); seen_events=set(); seen_sources=set()
    for i,c in enumerate(candidates):
        p=f"candidate_observations[{i}]"
        if not isinstance(c,Mapping): e.append(f"{p}: must be a mapping"); continue
        _closed(c,CAND_KEYS,p,e)
        for k in ("candidate_id","event_id","symbol","event_type","event_subtype","mechanism","scale","horizon","endpoint_status"):
            if not _text(c.get(k)): e.append(f"{p}.{k}: required")
        if c.get("horizon") not in HORIZONS: e.append(f"{p}.horizon: invalid horizon")
        if c.get("event_type")!=target.get("event_type") or c.get("event_subtype")!=target.get("event_subtype"): e.append(f"{p}: event class mismatch")
        canonical_prior = mode == "real" and c.get("event_id") == CANDIDATE_EVENT_ID
        if not canonical_prior and c.get("mechanism") != target.get("mechanism"): e.append(f"{p}.mechanism: incompatible case mechanism")
        if not canonical_prior and c.get("scale") != target.get("scale"): e.append(f"{p}.scale: incompatible case scale")
        cd=_day(c.get("effective_date"));
        if cd is None: e.append(f"{p}.effective_date: invalid date")
        elif td and cd>=td: e.append(f"{p}.effective_date: candidate must precede target")
        for k in ("operator_status",):
            if c.get(k) is not None and not _text(c.get(k)): e.append(f"{p}.{k}: null or nonempty text")
        if c.get("working_interest_pct") is not None and not _finite(c.get("working_interest_pct")): e.append(f"{p}.working_interest_pct: finite number or null")
        ed=_day(c.get("endpoint_date")); ea=_day(c.get("endpoint_available_on"))
        if c.get("endpoint_status")=="mature":
            if ed is None or ea is None: e.append(f"{p}: mature endpoint requires dates")
            if not _finite(c.get("outcome_return_pct")): e.append(f"{p}.outcome_return_pct: mature requires finite number")
        elif c.get("outcome_return_pct") is not None: e.append(f"{p}.outcome_return_pct: only mature may carry return")
        if ed and cd and ed<=cd: e.append(f"{p}.endpoint_date: must follow candidate date")
        if ed and td and ed>=td: e.append(f"{p}.endpoint_date: endpoint lookahead to target")
        if ea and td and ea>td: e.append(f"{p}.endpoint_available_on: evidence after target")
        if cutoff and (ed and ed>cutoff or ea and ea>cutoff): e.append(f"{p}: endpoint after cutoff")
        e += _source_errors(c.get("source"),str(mode),cutoff,f"{p}.source")
        s=c.get("source") if isinstance(c.get("source"),Mapping) else {}
        if s and s.get("event_id") != c.get("event_id"): e.append(f"{p}.source.event_id: must bind owning candidate event")
        if _day(s.get("date")) and cd and _day(s["date"])>cd: e.append(f"{p}.source.date: after candidate event")
        key=(c.get("candidate_id"),c.get("event_id"),s.get("id"),c.get("horizon"))
        if key in seen: e.append(f"{p}: duplicate candidate/event/source/horizon")
        seen.add(key)
        for label, value, bucket in (("candidate_id", c.get("candidate_id"), seen_ids), ("event_id", c.get("event_id"), seen_events), ("source", s.get("id"), seen_sources)):
            pair = (value, c.get("horizon"))
            if pair in bucket: e.append(f"{p}: duplicate {label}/horizon")
            bucket.add(pair)
        if mode == "real":
            # The sole retained candidate is the Peshawar working-interest notice.
            # Any caller drift must not rewrite its mechanism, scale, operator, or source.
            for k in ("candidate_id", "event_id", "symbol", "event_type", "event_subtype", "effective_date", "mechanism", "scale", "operator_status"):
                if c.get(k) != REAL_CANDIDATE.get(k):
                    e.append(f"{p}.{k}: does not match canonical retained candidate")
            cs = c.get("source") or {}
            for k, v in REAL_CANDIDATE["source"].items():
                if cs.get(k) != v:
                    e.append(f"{p}.source.{k}: does not match canonical retained candidate source")
        elif mode == "fixture":
            expected_date = ("2023-01-01", "2023-06-01", "2024-01-01")[i] if i < 3 else None
            if expected_date is None or c.get("candidate_id") != f"fixture-candidate-{i+1}" or c.get("event_id") != f"fixture-event-{i+1}" or c.get("effective_date") != expected_date or c.get("endpoint_status") != "mature" or c.get("outcome_return_pct") != float(i+1):
                e.append(f"{p}: fixture observation is not an exact sealed fixture")
            if s.get("id") != f"fixture:candidate-{i+1}" or s.get("event_id") != c.get("event_id"):
                e.append(f"{p}.source: fixture source binding mismatch")
    if BANNED and any(x in _walk_text(payload) for x in BANNED): e.append("payload: banned financial/causal/advice language")
    try: json.dumps(payload,allow_nan=False,sort_keys=True)
    except (TypeError,ValueError): e.append("payload: JSON must be finite and serializable")
    return sorted(set(e))

def fingerprint(c: Mapping[str,Any])->str:
    return hashlib.sha256(json.dumps(c,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
