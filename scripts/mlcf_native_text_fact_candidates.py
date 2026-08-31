#!/usr/bin/env python3
"""Audit-only consolidated MLCF fact-candidate extraction."""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
import pymupdf
ROOT=Path(__file__).resolve().parents[1]; MAN=ROOT/'config/mlcf_official_intake_manifest.json'; BASE=ROOT/'.cache/company_intel/mlcf_official_intake'; OUT=ROOT/'state/company_intel/mlcf_native_text_fact_candidates.json'; REVIEW=ROOT/'state/company_intel/mlcf_native_text_statement_review_receipt.json'
FILES={'psx:194111':'194111.pdf','issuer:mlcf:1q-2021-09':'q1_2021.pdf','issuer:mlcf:hy-2021-12':'hy_2021.pdf','issuer:mlcf:q3-2022-03':'q3_2022.pdf'}
PAT={'revenue':re.compile(r'^(?:sales\s*-\s*net|net\s+sales|revenue)\b',re.I),'profit_after_tax_attributable':re.compile(r'^profit\s+after\s+tax(?:ation)?\b',re.I),'basic_eps':re.compile(r'^(?:earnings?\s+per\s+share|basic\s+eps)\b',re.I),'operating_cash_flow':re.compile(r'^(?:net\s+)?cash\s+(?:generated\s+from|provided\s+by)\s+operating\s+activities\b',re.I)}
def main():
 m=json.loads(MAN.read_text(encoding='utf-8')); review=json.loads(REVIEW.read_text(encoding='utf-8')); review_pages={d['document_id']:{p['page'] for p in d.get('selected_statement_pages',[])} for d in review.get('documents',[])}; rows={x['document_id']:x for x in m['documents']}; docs=[]; counts={}
 for did,fn in FILES.items():
  row=rows[did]; raw=(BASE/fn).read_bytes(); digest=hashlib.sha256(raw).hexdigest()
  if digest!=row['content_sha256']: raise ValueError(f'{did}: hash mismatch')
  pdf=pymupdf.open(stream=raw,filetype='pdf'); cs=[]; omitted=[]; duration=12 if row['period_type']=='annual' else (3 if row['period_end'].endswith('-09-30') else 6 if row['period_end'].endswith('-12-31') else 9)
  for i,page in enumerate(pdf):
   text=' '.join(page.get_text().split()); up=text.upper()
   if i+1 not in review_pages.get(did,set()) or 'CONSOLIDATED' not in up or 'UNCONSOLIDATED' in up: continue
   scale=1000 if re.search(r"RUPEES?\s+IN\s+(?:THOUSAND|'000)",up) else 1
   for block in page.get_text('blocks'):
    label=' '.join(str(block[4]).split()); metric=next((k for k,p in PAT.items() if p.search(label)),None)
    if not metric: continue
    if metric in {'revenue','profit_after_tax_attributable','basic_eps'} and 'STATEMENT OF PROFIT OR LOSS' not in up: continue
    if metric=='operating_cash_flow' and 'CASH FLOWS FROM OPERATING ACTIVITIES' not in up: continue
    vals=[]
    for token in re.findall(r'(?<![A-Za-z])\(?-?\d[\d,]*(?:\.\d+)?\)?',label):
     neg=token.startswith('(') and token.endswith(')'); val=float(token.strip('()').replace(',','')); vals.append(-val if neg else val)
    if metric=='basic_eps': vals=[v for v in vals if abs(v)<100]
    if len(vals)!=1: omitted.append({'page':i+1,'label':label,'reason':'no_unambiguous_numeric_cell' if not vals else 'multiple_numeric_cells_ambiguous'}); continue
    cs.append({'metric':metric,'label':label,'raw_value':vals[0],'normalized_value':vals[0] if metric=='basic_eps' else vals[0]*scale,'unit':'PKR/share' if metric=='basic_eps' else 'PKR','scale':scale,'statement_identity':'consolidated','period_end':row['period_end'],'duration_months':duration,'original_page':i+1,'geometry':{'x0':round(block[0],1),'y0':round(block[1],1),'x1':round(block[2],1),'y1':round(block[3],1)},'content_sha256':digest,'source_url':row['source_url'],'status':'audit_only','promotion_status':'blocked'})
  counts[did]={k:sum(c['metric']==k for c in cs) for k in PAT}; docs.append({'document_id':did,'raw_path':str((BASE/fn).relative_to(ROOT)).replace('\\','/'),'source_url':row['source_url'],'content_sha256':digest,'content_length':len(raw),'page_count':len(pdf),'candidates':cs,'omitted':omitted,'promotion_status':'audit_only'})
 out={'schema_version':1,'receipt_version':'mlcf_native_text_fact_candidates_v1','symbol':'MLCF','manifest':'config/mlcf_official_intake_manifest.json','policy':{'local_originals_only':True,'consolidated_only':True,'native_text_geometry_required':True,'no_network':True,'no_ocr':True,'audit_only':True,'facts_promoted':False,'coverage_changed':False,'case_changed':False},'documents':docs,'candidate_counts':counts,'summary':{'total_candidates':sum(sum(v.values()) for v in counts.values()),'facts':[],'promotion_status':'blocked'}}
 OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print('wrote',OUT.relative_to(ROOT))
if __name__=='__main__': main()
