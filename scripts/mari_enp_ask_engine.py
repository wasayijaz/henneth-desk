"""Deterministic Ask Henneth responses for the MARI Peshawar E&P case.

Connects mari_enp_valuation_engine and mari_enp_scenario_lab to a fixed
investor Q&A set. Every numeric clause is copied from those kernels.
Retained MARI state stays fail-closed until financial truth is qualified
and assumptions are approved. Research text only: no advice, no orders.
"""
from __future__ import annotations

from typing import Any, Mapping
import hashlib
import json
import re
from pathlib import Path

from psx_data import ROOT, STATE, load_json, save_json
import mari_enp_valuation_engine as nav
import mari_enp_scenario_lab as lab

ENGINE_VERSION = "mari_enp_ask_engine_v1"
FORMULA_ID = "enp_exploration.ask_henneth.v1"
RESULT_SCHEMA = "mari_enp_ask_engine_result_v1"
CASE_ID = nav.CASE_ID
SYMBOL = nav.SYMBOL
CASE_FAMILY = nav.CASE_FAMILY
OUT = STATE / "company_intel" / "mari_enp_ask_engine.json"

STATUS_COMPUTED = "computed"
STATUS_TRUTH = "blocked_financial_truth_not_qualified"
STATUS_MISSING = "blocked_missing_inputs"
STATUS_OBSERVED = "observed_only"

SECTION_SPECS = (
    ("conclusion", "Conclusion"),
    ("observed_evidence", "Observed evidence"),
    ("business_mechanism", "Business mechanism"),
    ("historical_benchmark", "Historical benchmark"),
    ("financial_impact", "Financial impact"),
    ("scenario_range", "Scenario range"),
    ("valuation_impact", "Valuation impact"),
    ("current_price_expectations", "Current-price expectations"),
    ("confidence", "Confidence"),
    ("what_to_watch", "What to watch"),
)
SECTION_KEYS = tuple(key for key, _title in SECTION_SPECS)

QUESTIONS = (
    ("why_acquire", "Why is MARI acquiring working interest in Peshawar Block?"),
    ("well_cost_next_four_quarters", "What could the exploration well cost during the next four quarters?"),
    ("first_production_timing", "When could commercial production begin if successful?"),
    ("unrisked_vs_dry_hole", "What is the unrisked discovery value vs dry-hole cost?"),
    ("per_share_scenarios", "What is the event worth per share across bear, base, bull?"),
    ("implied_discovery_probability", "What discovery probability does the current price imply?"),
    ("invalidating_evidence", "Which future evidence would invalidate the case?"),
)

INVALIDATORS = (
    "An official Peshawar Block well result reported as dry or non-commercial.",
    "An official filing that reduces, exits, or transfers the reported working interest or operatorship.",
    "Source-qualified reserves, well cost, or timing outside the explicit bear/base/bull envelope.",
    "A qualified share-count or tax/royalty restatement that breaks the modelled operands.",
    "Financial truth remaining not qualified, which keeps every numeric Ask response blocked.",
)

_ADVICE_RE = re.compile(r"\b(?:buy|sell|accumulate|target\s+price|price\s+target|you\s+should)\b", re.I)

ENVELOPE_KEYS = (
    "schema_version",
    "formula_id",
    "engine_version",
    "valuation_engine_version",
    "scenario_lab_engine_version",
    "case_id",
    "symbol",
    "case_family",
    "status",
    "blocked_reasons",
    "missing_inputs",
    "financial_truth_status",
    "assumptions_approved",
    "run_receipt",
    "questions",
    "confidence_limitations",
    "policy",
)


def _q(value: float) -> str:
    return format(float(value), ".8g")


def _section(key: str, status: str, text: str, numbers: dict[str, Any] | None) -> dict[str, Any]:
    title = dict(SECTION_SPECS)[key]
    if _ADVICE_RE.search(text):
        raise ValueError(f"{key}: advice language is forbidden")
    return {
        "key": key,
        "title": title,
        "status": status,
        "text": text,
        "numbers": numbers,
    }


def _blocked_sections(reason: str, observed_text: str, watch_text: str, blocked: str = STATUS_MISSING) -> dict[str, Any]:
    numeric = (
        "financial_impact",
        "scenario_range",
        "valuation_impact",
        "current_price_expectations",
    )
    sections = {}
    for key, title in SECTION_SPECS:
        if key == "observed_evidence":
            sections[key] = _section(key, STATUS_OBSERVED, observed_text, None)
        elif key == "what_to_watch":
            sections[key] = _section(key, STATUS_OBSERVED, watch_text, None)
        elif key == "historical_benchmark":
            sections[key] = _section(
                key,
                STATUS_OBSERVED,
                "No qualifying same-company or peer analogue sample is retained for this case. Raw price context is descriptive only and is not a valuation input.",
                None,
            )
        elif key in numeric:
            sections[key] = _section(
                key,
                blocked,
                "Unknown. Numeric " + title.lower() + " is blocked because " + reason + ".",
                None,
            )
        elif key == "confidence":
            sections[key] = _section(
                key,
                blocked,
                "Confidence in modelled event value is withheld because " + reason + ".",
                None,
            )
        else:
            sections[key] = _section(
                key,
                blocked,
                "The desk does not quantify this question because " + reason + ".",
                None,
            )
    return sections


def _observed_bundle(root: Path | None = None) -> dict[str, Any]:
    payload = load_json((root or ROOT) / "state" / "company_intel" / "intelligence_cases.json", {})
    company = ((payload.get("companies") or {}).get(SYMBOL) or {})
    matches = [row for row in (company.get("cases") or []) if type(row) is dict and row.get("case_id") == CASE_ID]
    if not matches:
        return {
            "text": "No retained observed MARI Peshawar working-interest case seed is available.",
            "documents": [],
            "statements": [],
        }
    case = matches[0]
    statements = []
    documents = []
    for fact in case.get("observed_facts") or []:
        if type(fact) is dict and type(fact.get("statement")) is str:
            statements.append(fact["statement"])
        for evidence in fact.get("evidence") or []:
            if type(evidence) is not dict:
                continue
            documents.append(
                {
                    "document_id": evidence.get("document_id"),
                    "page": evidence.get("page"),
                    "content_sha256": evidence.get("content_sha256"),
                    "source_url": evidence.get("source_url"),
                }
            )
    text = " ".join(statements) if statements else "Observed Peshawar Block working-interest filings are retained without modelled economics."
    return {"text": text, "documents": documents, "statements": statements}


def _watch_text() -> str:
    return " ".join(INVALIDATORS)


def _next_four_quarter_well_cost(schedule: list[Mapping[str, Any]], fx: float) -> dict[str, float]:
    rows = [row for row in schedule if int(row["quarter_index"]) < 4]
    expl_usd = sum(float(row.get("exploration_capex_usd") or 0.0) for row in rows)
    return {
        "exploration_capex_next_four_quarters_usd": float(expl_usd),
        "exploration_capex_next_four_quarters_pkr": float(expl_usd) * fx,
    }


def _computed_sections(question_id: str, nav_result: Mapping[str, Any], lab_result: Mapping[str, Any], assumptions: Mapping[str, Any], observed: Mapping[str, Any]) -> dict[str, Any]:
    values = nav_result["values"]
    fx = float(assumptions["fx_pkr_usd"])
    delay = int(assumptions["first_production_delay_quarters"])
    well = _next_four_quarter_well_cost(nav_result["quarterly_schedule"], fx)
    scenarios = lab_result["scenarios"]
    bear_ps = scenarios["bear"]["values"]["per_share_risked_pkr"]
    base_ps = scenarios["base"]["values"]["per_share_risked_pkr"]
    bull_ps = scenarios["bull"]["values"]["per_share_risked_pkr"]
    gap = lab_result["expectations_gap"]
    p_base = float(scenarios["base"]["p_disc"])
    observed_text = observed["text"]
    watch_text = _watch_text()
    hist_text = "No qualifying analogue sample is retained. Historical raw-price windows are descriptive only and do not benchmark discovery NPV."
    mech_text = "The filings describe a farm-out of working interest with operatorship. Modelled cash flows scale production, opex and capex by working interest; operator_status does not change the arithmetic."
    conf_text = "Research arithmetic from approved assumptions and the MARI E&P kernels. Single-point estimates, no advice, no publication."

    def pack(conclusion: str, financial: tuple[str, dict | None], scenario: tuple[str, dict | None], valuation: tuple[str, dict | None], expectations: tuple[str, dict | None]) -> dict[str, Any]:
        return {
            "conclusion": _section("conclusion", STATUS_COMPUTED, conclusion, None),
            "observed_evidence": _section("observed_evidence", STATUS_OBSERVED, observed_text, None),
            "business_mechanism": _section("business_mechanism", STATUS_COMPUTED, mech_text, None),
            "historical_benchmark": _section("historical_benchmark", STATUS_OBSERVED, hist_text, None),
            "financial_impact": _section("financial_impact", STATUS_COMPUTED if financial[1] else STATUS_MISSING, financial[0], financial[1]),
            "scenario_range": _section("scenario_range", STATUS_COMPUTED if scenario[1] else STATUS_MISSING, scenario[0], scenario[1]),
            "valuation_impact": _section("valuation_impact", STATUS_COMPUTED if valuation[1] else STATUS_MISSING, valuation[0], valuation[1]),
            "current_price_expectations": _section(
                "current_price_expectations",
                STATUS_COMPUTED if expectations[1] else (gap.get("status") or STATUS_MISSING),
                expectations[0],
                expectations[1],
            ),
            "confidence": _section("confidence", STATUS_COMPUTED, conf_text, {"p_disc_base": p_base}),
            "what_to_watch": _section("what_to_watch", STATUS_OBSERVED, watch_text, None),
        }

    if question_id == "why_acquire":
        conclusion = "Retained filings report a Peshawar Block working-interest farm-out with operatorship. They do not state a reserves or NPV motive; modelled event value is the risked NAV of " + _q(values["risked_npv_pkr"]) + " PKR, not a stated acquisition rationale."
        return pack(
            conclusion,
            (
                "Base risked NPV is " + _q(values["risked_npv_pkr"]) + " PKR (" + _q(values["risked_npv_usd"]) + " USD).",
                {"risked_npv_pkr": values["risked_npv_pkr"], "risked_npv_usd": values["risked_npv_usd"]},
            ),
            (
                "Bear/base/bull risked NPV per share is " + _q(bear_ps) + " / " + _q(base_ps) + " / " + _q(bull_ps) + " PKR.",
                {"bear_per_share_risked_pkr": bear_ps, "base_per_share_risked_pkr": base_ps, "bull_per_share_risked_pkr": bull_ps},
            ),
            (
                "Unrisked discovery NPV is " + _q(values["unrisked_npv_pkr"]) + " PKR versus dry-hole cost " + _q(values["dry_hole_cost_pkr"]) + " PKR.",
                {"unrisked_npv_pkr": values["unrisked_npv_pkr"], "dry_hole_cost_pkr": values["dry_hole_cost_pkr"]},
            ),
            _gap_clause(gap, p_base),
        )
    if question_id == "well_cost_next_four_quarters":
        conclusion = "Modelled working-interest exploration capex over the next four quarters is " + _q(well["exploration_capex_next_four_quarters_pkr"]) + " PKR."
        numbers = well | {"well_cost_gross_usd": float(assumptions["well_cost"]), "working_interest": float(assumptions["working_interest"])}
        text = (
            "Gross well cost is "
            + _q(numbers["well_cost_gross_usd"])
            + " USD. Working interest "
            + _q(numbers["working_interest"])
            + " implies exploration capex of "
            + _q(well["exploration_capex_next_four_quarters_usd"])
            + " USD / "
            + _q(well["exploration_capex_next_four_quarters_pkr"])
            + " PKR in quarter indices 0-3."
        )
        return pack(conclusion, (text, numbers), ("Scenario labels do not change the explicit well-cost input.", None), (text, numbers), _gap_clause(gap, p_base))
    if question_id == "first_production_timing":
        conclusion = "If the well is commercially successful, modelled first production is at quarter index " + str(delay) + "."
        numbers = {
            "first_production_delay_quarters": float(delay),
            "drilling_duration_months": float(assumptions["drilling_duration_months"]),
        }
        text = (
            "Drilling duration is "
            + _q(numbers["drilling_duration_months"])
            + " months. Commercial production is modelled to start at first_production_delay_quarters="
            + _q(numbers["first_production_delay_quarters"])
            + "."
        )
        return pack(conclusion, (text, numbers), ("Bear/base/bull keep the same explicit production delay in this kernel.", None), (text, numbers), _gap_clause(gap, p_base))
    if question_id == "unrisked_vs_dry_hole":
        conclusion = "Unrisked discovery NPV is " + _q(values["unrisked_npv_pkr"]) + " PKR; dry-hole cost is " + _q(values["dry_hole_cost_pkr"]) + " PKR."
        numbers = {
            "unrisked_npv_pkr": values["unrisked_npv_pkr"],
            "unrisked_npv_usd": values["unrisked_npv_usd"],
            "dry_hole_cost_pkr": values["dry_hole_cost_pkr"],
            "dry_hole_cost_usd": values["dry_hole_cost_usd"],
            "p_disc": values["p_disc"],
            "risked_npv_pkr": values["risked_npv_pkr"],
        }
        text = (
            "Unrisked discovery value is "
            + _q(numbers["unrisked_npv_pkr"])
            + " PKR ("
            + _q(numbers["unrisked_npv_usd"])
            + " USD). Dry-hole cost is "
            + _q(numbers["dry_hole_cost_pkr"])
            + " PKR ("
            + _q(numbers["dry_hole_cost_usd"])
            + " USD). Base P_disc is "
            + _q(numbers["p_disc"])
            + " and risked NPV is "
            + _q(numbers["risked_npv_pkr"])
            + " PKR."
        )
        return pack(conclusion, (text, numbers), (text, numbers), (text, numbers), _gap_clause(gap, p_base))
    if question_id == "per_share_scenarios":
        conclusion = "Risked event value per share is " + _q(bear_ps) + " / " + _q(base_ps) + " / " + _q(bull_ps) + " PKR in bear/base/bull."
        numbers = {
            "bear_per_share_risked_pkr": bear_ps,
            "base_per_share_risked_pkr": base_ps,
            "bull_per_share_risked_pkr": bull_ps,
            "bear_risked_npv_pkr": scenarios["bear"]["values"]["risked_npv_pkr"],
            "base_risked_npv_pkr": scenarios["base"]["values"]["risked_npv_pkr"],
            "bull_risked_npv_pkr": scenarios["bull"]["values"]["risked_npv_pkr"],
        }
        text = (
            "Bear per-share risked value is "
            + _q(bear_ps)
            + " PKR, base is "
            + _q(base_ps)
            + " PKR, bull is "
            + _q(bull_ps)
            + " PKR. Corresponding risked NPVs are "
            + _q(numbers["bear_risked_npv_pkr"])
            + " / "
            + _q(numbers["base_risked_npv_pkr"])
            + " / "
            + _q(numbers["bull_risked_npv_pkr"])
            + " PKR."
        )
        return pack(conclusion, (text, numbers), (text, numbers), (text, numbers), _gap_clause(gap, p_base))
    if question_id == "implied_discovery_probability":
        clause, gap_numbers = _gap_clause(gap, p_base)
        if gap_numbers is None:
            conclusion = "Current-price discovery probability is blocked because the expectations gap is not computed."
        else:
            conclusion = "The current price implies P_market " + _q(gap_numbers["p_market"]) + " versus Henneth P_base " + _q(gap_numbers["p_base"]) + "; delta is " + _q(gap_numbers["delta"]) + "."
        return pack(conclusion, (clause, gap_numbers), (clause, gap_numbers), (clause, gap_numbers), (clause, gap_numbers))
    if question_id == "invalidating_evidence":
        conclusion = "The case is invalidated by official well failure, working-interest exit, operand restatement, or continued unqualified financial truth."
        return pack(
            conclusion,
            ("No numeric invalidation threshold is invented beyond the explicit bear/base/bull envelope already modelled.", None),
            (
                "Bear/base/bull remain the explicit modelled envelope ("
                + _q(bear_ps)
                + " / "
                + _q(base_ps)
                + " / "
                + _q(bull_ps)
                + " PKR per share); evidence outside that envelope invalidates the numeric run.",
                {"bear_per_share_risked_pkr": bear_ps, "base_per_share_risked_pkr": base_ps, "bull_per_share_risked_pkr": bull_ps},
            ),
            ("Numeric event value is not used as a kill-switch; official filings are.", None),
            _gap_clause(gap, p_base),
        )
    raise ValueError("unknown question_id")


def _gap_clause(gap: Mapping[str, Any], p_base: float) -> tuple[str, dict[str, Any] | None]:
    if gap.get("status") != STATUS_COMPUTED or gap.get("p_market") is None:
        reason = "; ".join(gap.get("blocked_reasons") or ["market inputs missing"])
        return "Current-price expectations are blocked: " + reason + ".", None
    numbers = {
        "p_base": float(gap["p_base"]),
        "p_market": float(gap["p_market"]),
        "delta": float(gap["delta"]),
        "market_premium_pkr_per_share": float(gap["market_premium_pkr_per_share"]),
    }
    text = (
        "P_base is "
        + _q(numbers["p_base"])
        + ". P_market is "
        + _q(numbers["p_market"])
        + ". Expectations gap delta is "
        + _q(numbers["delta"])
        + " from a premium of "
        + _q(numbers["market_premium_pkr_per_share"])
        + " PKR per share."
    )
    return text, numbers


def _question_row(question_id: str, question: str, sections: Mapping[str, Any]) -> dict[str, Any]:
    if tuple(sections) != SECTION_KEYS:
        raise ValueError("answer sections must follow the required order")
    return {
        "question_id": question_id,
        "question": question,
        "sections": dict(sections),
    }


def _limitations() -> dict[str, Any]:
    return {
        "research_only": True,
        "no_advice": True,
        "single_point_estimate": True,
        "simplifications": [
            "Ask text copies kernel outputs; it does not re-derive DCF identities",
            "Observed evidence is retained filing language and is not a modelled motive",
            "Historical analogue samples below the n<3 threshold are not used as NPV benchmarks",
            "Invalidating evidence is a closed official-filing list, not a probability",
        ],
    }


def _policy() -> dict[str, Any]:
    return {
        "research_only": True,
        "no_advice": True,
        "no_order": True,
        "fail_closed_without_qualified_financial_truth": True,
        "fail_closed_without_approved_assumptions": True,
        "synthetic_numbers_not_written_to_retained_state": True,
    }


def _blank_envelope(status: str, reasons: list[str], missing: list[str], truth_status: str, approved: bool, questions: list[dict[str, Any]], identity: Mapping[str, Any] | None = None) -> dict[str, Any]:
    identity = identity or {}
    return {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "engine_version": ENGINE_VERSION,
        "valuation_engine_version": nav.ENGINE_VERSION,
        "scenario_lab_engine_version": lab.ENGINE_VERSION,
        "case_id": identity.get("case_id") or CASE_ID,
        "symbol": identity.get("symbol") or SYMBOL,
        "case_family": CASE_FAMILY,
        "status": status,
        "blocked_reasons": sorted(set(str(reason) for reason in reasons if type(reason) is str and reason)),
        "missing_inputs": sorted(set(missing)),
        "financial_truth_status": truth_status,
        "assumptions_approved": approved,
        "run_receipt": {"inputs_sha256": None, "contract_version": ENGINE_VERSION},
        "questions": questions,
        "confidence_limitations": _limitations(),
        "policy": _policy(),
    }


def evaluate_ask(case: Mapping[str, Any], root: Path | None = None) -> dict[str, Any]:
    """Return the seven canonical answers, computed or fail-closed."""
    identity = {
        "case_id": (case.get("case_id") if type(case) is dict else None) or CASE_ID,
        "symbol": (case.get("symbol") if type(case) is dict else None) or SYMBOL,
    }
    observed = _observed_bundle(root)
    watch_text = _watch_text()
    if type(case) is not dict:
        questions = [
            _question_row(qid, question, _blocked_sections("the request is not a mapping", observed["text"], watch_text))
            for qid, question in QUESTIONS
        ]
        return _blank_envelope(STATUS_MISSING, ["case: must be an exact mapping"], ["assumptions"], "unknown", False, questions, identity)

    truth_qualified = case.get("financial_truth_qualified") is True
    approved = case.get("assumptions_approved") is True
    if not truth_qualified or not approved:
        reason = "financial truth is not qualified" if not truth_qualified else "assumptions are unapproved"
        reasons = []
        if not truth_qualified:
            reasons.append("financial_truth_not_qualified")
        if not approved:
            reasons.append("assumptions_unapproved")
        questions = [
            _question_row(qid, question, _blocked_sections(reason, observed["text"], watch_text, STATUS_TRUTH))
            for qid, question in QUESTIONS
        ]
        missing = list(nav.REQUIRED_FIELDS)
        if "scenarios" not in case:
            missing.append("scenarios")
        if "grids" not in case:
            missing.append("grids")
        return _blank_envelope(
            STATUS_TRUTH,
            reasons,
            missing,
            "qualified" if truth_qualified else "not_qualified",
            approved,
            questions,
            identity,
        )

    lab_result = lab.evaluate_lab(case)
    if lab_result.get("status") != STATUS_COMPUTED:
        reason = "scenario lab did not compute"
        questions = [
            _question_row(qid, question, _blocked_sections(reason, observed["text"], watch_text, lab_result.get("status") or STATUS_MISSING))
            for qid, question in QUESTIONS
        ]
        return _blank_envelope(
            lab_result.get("status") or STATUS_MISSING,
            list(lab_result.get("blocked_reasons") or [reason]),
            list(lab_result.get("missing_inputs") or []),
            "qualified",
            True,
            questions,
            identity,
        )

    base_params = case["scenarios"]["base"]
    nav_result = nav.compute_valuation(lab.apply_scenario_params(case["assumptions"], base_params))
    questions = [
        _question_row(qid, question, _computed_sections(qid, nav_result, lab_result, case["assumptions"], observed))
        for qid, question in QUESTIONS
    ]
    canonical = json.dumps(
        {"assumptions": case["assumptions"], "scenarios": case["scenarios"], "grids": case["grids"], "market": case.get("market")},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "engine_version": ENGINE_VERSION,
        "valuation_engine_version": nav.ENGINE_VERSION,
        "scenario_lab_engine_version": lab.ENGINE_VERSION,
        "case_id": identity["case_id"],
        "symbol": identity["symbol"],
        "case_family": CASE_FAMILY,
        "status": STATUS_COMPUTED,
        "blocked_reasons": [],
        "missing_inputs": [],
        "financial_truth_status": "qualified",
        "assumptions_approved": True,
        "run_receipt": {
            "inputs_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "contract_version": ENGINE_VERSION,
        },
        "questions": questions,
        "confidence_limitations": _limitations(),
        "policy": _policy(),
    }


def _mari_truth(root: Path | None = None) -> dict[str, Any]:
    payload = load_json((root or ROOT) / "state" / "company_intel" / "financial_truth_qualification.json", {})
    row = ((payload.get("companies") or {}).get(SYMBOL) or {})
    return row if type(row) is dict else {}


def _enp_assumptions_approved(root: Path | None = None) -> bool:
    payload = load_json((root or ROOT) / "state" / "company_intel" / "financial_engine_assumptions.json", {})
    records = payload.get("records") if type(payload) is dict else None
    if type(records) is not list:
        return False
    for record in records:
        if type(record) is not dict or record.get("symbol") != SYMBOL or record.get("approved") is not True:
            continue
        metric = str(record.get("metric") or record.get("assumption") or record.get("label") or "")
        if any(token in metric.lower() for token in ("enp", "peshawar", "working_interest", "risked_nav")):
            return True
    return False


def build_retained_ask(root: Path | None = None, *, write: bool = False) -> dict[str, Any]:
    """Fail-closed retained MARI Ask envelope. Never invents event economics."""
    root = root or ROOT
    truth = _mari_truth(root)
    qualified = truth.get("status") == "qualified"
    approved = _enp_assumptions_approved(root)
    envelope = evaluate_ask(
        {
            "symbol": SYMBOL,
            "case_id": CASE_ID,
            "financial_truth_qualified": qualified,
            "assumptions_approved": approved,
            "assumptions": {},
        },
        root=root,
    )
    extra = ["no_model_ready_E_and_P_operands"]
    if not qualified:
        tie = truth.get("financial_tie_out") or {}
        extra.append("financial_truth_not_qualified: " + str(tie.get("reason") or "financial truth is not qualified"))
    if not approved:
        extra.append("assumptions_unapproved")
    envelope["blocked_reasons"] = sorted(set(list(envelope["blocked_reasons"]) + extra))
    if write:
        save_json(root / "state" / "company_intel" / "mari_enp_ask_engine.json", envelope)
    return envelope


def build(*, write: bool = True) -> dict[str, Any]:
    return build_retained_ask(ROOT, write=write)


def main() -> None:
    envelope = build(write=True)
    print(f"mari_enp_ask_engine: {envelope['status']} -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
