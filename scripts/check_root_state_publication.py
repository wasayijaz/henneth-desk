#!/usr/bin/env python3
"""Verify the root desk never serves CI-owner-only state artifacts."""
import os
import re
import sys

from root_state_publication import (
    CI_PRIVATE_STATE_FILES,
    CI_PRIVATE_STATE_PREFIXES,
    is_ci_private_state_path,
    normalize_state_path,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_text(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def fail(message):
    print(f"x {message}")
    return False


def quoted_values(source, const_name):
    match = re.search(
        rf"const\s+{re.escape(const_name)}\s*=\s*(?:new\s+Set\()?(\[[^\]]*\])\)?;",
        source,
        flags=re.S,
    )
    if not match:
        return None
    return tuple(re.findall(r"['\"]([^'\"]+)['\"]", match.group(1)))


def main():
    ok = True

    required_private = (
        "company_documents.json",
        "company_briefs.json",
        "company_brief_receipts.json",
        "document_synthesis_queue.json",
        "company_intel/source_registry.json",
        "/state/company_intel/company_graph.json",
        "state\\company_intel\\change_intelligence.json",
        "company_intel%2Fdriver_graphs.json",
        "company_intel%252Ffinancial_model_inputs.json",
    )
    legitimate_root_state = (
        "health.json",
        "/state/rooms.json",
        "state/history/LUCK.json",
        "natal_ephem.json",
        "company_profiles.json",
        "company_financial_series.json",
        "company_source_qa.json",
        "company_event_ledger.json",
    )
    unsafe_paths = (
        "../company_documents.json",
        "company_intel/../health.json",
        "%2e%2e/company_documents.json",
    )

    for path in required_private:
        if not is_ci_private_state_path(path):
            ok = fail(f"{path}: expected CI-private classification") and ok
    for path in legitimate_root_state:
        if is_ci_private_state_path(path):
            ok = fail(f"{path}: ordinary root state was classified CI-private") and ok
    for path in unsafe_paths:
        if not is_ci_private_state_path(path):
            ok = fail(f"{path}: unsafe traversal must fail closed") and ok

    if normalize_state_path("state%2Fcompany_intel%2Fsource_registry.json") != "company_intel/source_registry.json":
        ok = fail("encoded state/company_intel path did not normalize to the private prefix") and ok

    middleware = read_text("middleware.js")
    js_files = quoted_values(middleware, "CI_PRIVATE_STATE_FILES")
    js_prefixes = quoted_values(middleware, "CI_PRIVATE_STATE_PREFIXES")
    if js_files is None:
        ok = fail("middleware.js: missing CI_PRIVATE_STATE_FILES") and ok
    elif tuple(js_files) != CI_PRIVATE_STATE_FILES:
        ok = fail("middleware.js: CI_PRIVATE_STATE_FILES does not match root_state_publication.py") and ok
    if js_prefixes is None:
        ok = fail("middleware.js: missing CI_PRIVATE_STATE_PREFIXES") and ok
    elif tuple(js_prefixes) != CI_PRIVATE_STATE_PREFIXES:
        ok = fail("middleware.js: CI_PRIVATE_STATE_PREFIXES does not match root_state_publication.py") and ok
    if "isCiPrivateStatePath(file)" not in middleware:
        ok = fail("middleware.js: CI-private classifier is not enforced in the request path") and ok

    build = read_text("scripts/vercel_build.sh")
    copy_index = build.find("cp -r state public/state")
    if copy_index < 0:
        ok = fail("scripts/vercel_build.sh: state copy command not found") and ok
    if "cp -r config" in build or "cp -R config" in build:
        ok = fail("scripts/vercel_build.sh: config directory must never be copied to public") and ok
    for rel in CI_PRIVATE_STATE_FILES:
        token = f"public/state/{rel}"
        rm_index = build.find(token)
        if rm_index < 0:
            ok = fail(f"scripts/vercel_build.sh: missing removal for {token}") and ok
        elif copy_index >= 0 and rm_index < copy_index:
            ok = fail(f"scripts/vercel_build.sh: removal for {token} runs before state copy") and ok
    for prefix in CI_PRIVATE_STATE_PREFIXES:
        token = "public/state/" + prefix.rstrip("/")
        rm_index = build.find(token)
        if rm_index < 0:
            ok = fail(f"scripts/vercel_build.sh: missing removal for {token}") and ok
        elif copy_index >= 0 and rm_index < copy_index:
            ok = fail(f"scripts/vercel_build.sh: removal for {token} runs before state copy") and ok

    serve = read_text("scripts/serve.py")
    if "config/desk.json" not in serve or "must never be served" not in serve:
        ok = fail("scripts/serve.py: config/desk.json local-serving guard missing") and ok

    if not ok:
        sys.exit(1)
    print("ok root state publication boundary")


if __name__ == "__main__":
    main()
