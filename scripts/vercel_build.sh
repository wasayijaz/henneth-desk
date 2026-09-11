#!/bin/sh
set -e
mkdir -p public
# Ship the WHOLE dashboard, then drop what must not be public. This used to be an explicit
# allow-list of 18 filenames, and on 2026-08-14 that cost a live outage: auth-terminal.js and
# auth-terminal.css were added to dashboard/ but not to the list, so they 404'd in production
# while index.html and app.js shipped fine — the sign-in screen had nothing to mount and every
# signed-out visitor got a blank page. An allow-list fails silently and fails CLOSED on exactly
# the file a release is about. A deny-list fails loudly (a stray file is visible, not missing).
# Vercel builds from the git checkout, so untracked scratch files in dashboard/ never reach here.
cp -r dashboard/. public/
# app.html is a stale duplicate shell predating the sign-in gate; it is deliberately not served.
rm -f public/app.html
cp -r state public/state
# CI-owner-only artifacts belong to the separate ci.henneth.app project. The root desk
# serves ordinary /state behind account auth, but it must not ship CI private state at all.
rm -rf public/state/company_intel \
  public/state/company_documents.json \
  public/state/company_briefs.json \
  public/state/company_brief_receipts.json \
  public/state/document_synthesis_queue.json
printf '' > public/.nojekyll
