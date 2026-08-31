#!/usr/bin/env python3
"""Focused fail-closed checker."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'state/company_intel/mlcf_native_text_fact_candidates.json'; MAN=ROOT/'config/mlcf_official_intake_manifest.json'; REVIEW=ROOT/'state/company_intel/mlcf_native_text_statement_review_receipt.json'
def main():
 r=json.loads(OUT.read_text(encoding='utf-8')); m=json.loads(MAN.read_text(encoding='utf-8')); rv=json.loads(REVIEW.read_text(encoding='utf-8')); allowed={d['document_id']:{p['page'] for p in d.get('selected_statement_pages',[])} for d in rv.get('documents',[])}; rows={x['document_id']:x for x in m['documents']}; docs=r.get('documents',[])
 assert r.get('receipt_version')=='mlcf_native_text_fact_candidates_v1' and len(docs)==4
 for k in ('local_originals_only','consolidated_only','native_text_geometry_required','no_network','no_ocr','audit_only'): assert r['policy'][k] is True
 assert all(r['policy'][k] is False for k in ('facts_promoted','coverage_changed','case_changed'))
 for d in docs:
  row=rows[d['document_id']]; assert hashlib.sha256((ROOT/d['raw_path']).read_bytes()).hexdigest()==row['content_sha256']==d['content_sha256']
  assert d['promotion_status']=='audit_only'
  for c in d['candidates']:
   assert c['statement_identity']=='consolidated' and c['status']=='audit_only' and c['promotion_status']=='blocked' and c['source_url']==row['source_url'] and c['content_sha256']==row['content_sha256'] and c['normalized_value'] is not None and c['original_page'] in allowed[d['document_id']] and c['geometry']
   assert not any(k in c for k in ('facts','metrics','values'))
 assert r['summary']['facts']==[] and r['summary']['promotion_status']=='blocked'; print('mlcf_native_text_fact_candidates: PASS'); return 0
if __name__=='__main__': raise SystemExit(main())
