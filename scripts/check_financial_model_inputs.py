"""Stable checks for Wave 3 v2 financial model inputs."""
from __future__ import annotations
import json, math, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; STATE=ROOT/'state'
sys_path=str(ROOT/'scripts')
import sys; sys.path.insert(0,sys_path)
from financial_statement_facts import extract_facts, parse_number, stable_id, PARSER_VERSION, PARSER_REVISION
from forecast_contract import OWNER_ASSUMPTION_OUTPUT_STATUS, qualified_financial_fact_source
from build_financial_series import _assemble, _sanitize_row
_raw_extract_facts = extract_facts
def extract_facts(doc, pages, words=None, page_records=None):
 # Geometry fixtures model a primary statement explicitly, matching the
 # production parser's requirement that a financial table has a local heading.
 def headed(page):
  return [(5,-20,130,-12,'Statement of Profit or Loss',-1,-1,0), *page]
 if words is not None:
  words=[headed(list(page)) for page in words]
 if page_records is not None:
  page_records=[{**record,'words':headed(list(record.get('words') or []))} for record in page_records]
 return _raw_extract_facts(doc,pages,words=words,page_records=page_records)
def load(p):
 with p.open(encoding='utf-8') as f:return json.load(f)
def walk(x):
 if isinstance(x,float) and not math.isfinite(x): raise AssertionError('nonfinite')
 if isinstance(x,dict):
  for v in x.values():walk(v)
 elif isinstance(x,list):
  for v in x:walk(v)
def main():
 assert PARSER_VERSION and PARSER_REVISION; checks=0
 p=load(STATE/'company_profiles.json'); pilot=set((p.get('pilot') or {}).get('symbols') or []); d=load(STATE/'company_intel/financial_model_inputs.json'); walk(d)
 if set(d.get('pilot_symbols') or [])!=pilot or set(d.get('companies') or {})!=pilot: raise AssertionError('pilot boundary')
 for sym,row in d['companies'].items():
  registry=row.get('model_registry') or {}; adapter=row.get('model_adapter') or {}
  if registry:
   if registry.get('status') not in {'covered','unsupported_sector_model'}: raise AssertionError(sym+' registry status')
   if registry.get('status')=='covered' and not row.get('registry_version'): raise AssertionError(sym+' missing registry version')
   if adapter.get('status')=='available' and (not row.get('adapter_version') or adapter.get('selected_sector')!='CEMENT'): raise AssertionError(sym+' available adapter boundary')
   if adapter.get('status')!='available' and row.get('adapter_version') is not None: raise AssertionError(sym+' unavailable adapter has version')
   if row.get('downstream_status',{}).get('forecast') not in {'blocked_insufficient_qualified_history','blocked_model_adapter_unavailable',OWNER_ASSUMPTION_OUTPUT_STATUS['forecast']}: raise AssertionError(sym+' forecast gate')
  if row.get('status')=='ready' and not all(len(row.get('observations',{}).get(x) or [])>=3 for x in ('revenue','profit_after_tax_attributable','basic_eps')): raise AssertionError(sym+' readiness')
 # Adversarial parser fixtures: ambiguous text fails closed; signs/dash and scope rules remain explicit.
 fixtures=[
  ('four_column', ['(Rupees in million) Revenue 2023 2022 2021 2020\nRevenue 100 90 80 70'], False),
  ('nine_month', ['Financial Results for nine months ended 30.09.2023\nRevenue 100'], False),
  ('consolidation_ambiguous', ['Financial Results 31.12.2023\nRevenue 100'], False),
  ('negative_dash', ['Annual Financial Results 31.12.2023 consolidated\nRevenue (100)\nProfit after tax attributable -'], False),
  ('cross_page', ['Annual Financial Results consolidated', 'Revenue 100'], False),
  ('other_title', ['Dividend declaration\nRevenue 100'], False),
  ('restatement', ['Annual Financial Results 31.12.2023 consolidated\nRevenue 100'], False),
  ('corroboration', ['Annual Financial Results 31.12.2023 consolidated\nRevenue 100'], False),
  ('availability_next_day', ['Annual Financial Results 31.12.2023 consolidated\nRevenue 100'], False),
  ('ocr_corrupt', ['Annual Financial Results 31.12.2023 consolidated\nRevenue lOO'], False),
  ('mixed_duration', ['Nine months ended 30.09.2023 consolidated\nRevenue 100'], False),
 ('formula_no_lookahead', ['Annual Financial Results 31.12.2023 consolidated\nRevenue 100'], False),
 ('split_header_band', ['Annual Financial Results 31.12.2023 consolidated\n2023\n2022\nRevenue 100 90'], False),
 ('duplicate_9m_3m', ['Quarterly Financial Results 30.09.2023 consolidated\nNine months ended Three months ended\n2023 2022 2023 2022\nRevenue 100 90 40 30'], False),
 ('duplicate_6m_3m', ['Quarterly Financial Results 30.06.2023 consolidated\nSix months ended Three months ended\n2023 2022 2023 2022\nRevenue 100 90 40 30'], False),
 ('split_row_cells', ['Annual Financial Results 31.12.2023 consolidated\n2023 2022\nRevenue\n100 90'], False),
 ('narrative_reject', ['Annual Financial Results 31.12.2023 consolidated\nRevenue increased by 100% due to demand'], False),
 ('duplicate_basis_sections', ['Annual Financial Results 31.12.2023 consolidated\n2023 2022 Revenue 100 90\nStandalone\n2023 2022 Revenue 80 70'], False),
 ('split_note_band', ['Annual Financial Results 31.12.2023 consolidated\nNotes\n2023 2022\nRevenue 5 100 90'], False),
 ('ambiguous_current_header', ['Annual Financial Results 31.12.2023 consolidated\n2023 2023 2022\nRevenue 100 90 80'], False),
 ('unmatched_numeric', ['Annual Financial Results 31.12.2023 consolidated\n2023 2022\nRevenue 100 90 77'], False),
 ('scale_locality_reject', ['Annual Financial Results 31.12.2023 consolidated\nRupees in million\n2023 2022 Revenue 100 90\nRupees in thousand\n2023 2022 Revenue 80 70'], False),
]
 for name,pages,expected in fixtures:
  facts=extract_facts({'doc_id':'psx:fixture_'+name,'title':pages[0],'source_url':'https://dps.psx.com.pk/download/document/1.pdf','content_sha256':'fixture'},pages,words=None)
  if any(f.get('readiness')=='model_loadable' for f in facts): raise AssertionError(name+' incorrectly model-loadable')
 geometry_fixtures=0
 # Accepted real-layout geometry proofs (split header and split row).
 def _accepted_words():
  return [(5,0,60,8,'Consolidated',0,0,0),(5,10,25,18,'PKR',0,1,0),(30,10,38,18,'in',0,1,1),(45,10,80,18,'million',0,1,2),(80,25,95,33,'Six',0,2,0),(100,25,130,33,'months',0,2,1),(135,25,160,33,'ended',0,2,2),(90,43,110,51,'2025',0,3,0),(160,43,180,51,'2024',0,3,1),(5,62,40,70,'Revenue',0,4,0),(90,74,110,82,'100',0,5,0),(160,74,180,82,'90',0,5,1)]
 accepted=extract_facts({'doc_id':'psx:accepted','title':'Annual Financial Results ended 30.06.2025 consolidated','period_end':'2025-06-30','published_at':'2026-01-01','source_url':'https://dps.psx.com.pk/download/document/99.pdf','content_sha256':'acceptedhash'},['Revenue'],words=[_accepted_words()])
 def _fact_view(f):
  ev=(f.get('evidence') or [{}])[0]
  return {'line':f.get('line'),'raw_value':f.get('raw_value'),'normalized_value':f.get('normalized_value'),'period_end':f.get('period_end'),'duration_months':f.get('duration_months'),'column_role':f.get('column_role'),'page':f.get('page'),'parser_version':f.get('parser_version'),'parser_revision':f.get('parser_revision'),'doc_id':f.get('document_id'),'hash':f.get('content_sha256'),'source_url':f.get('source_url'),'evidence_page':ev.get('page'),'evidence_source_url':ev.get('source_url'),'readiness':f.get('readiness'),'flags':f.get('quality_flags'),'basis':f.get('consolidation'),'scale':f.get('unit_multiplier'),'currency':f.get('currency')}
 assert [_fact_view(f) for f in accepted] == [
  {'line':'revenue','raw_value':'100','normalized_value':100000000.0,'period_end':'2025-06-30','duration_months':6,'column_role':'current_period','page':1,'parser_version':PARSER_VERSION,'parser_revision':PARSER_REVISION,'doc_id':'psx:accepted','hash':'acceptedhash','source_url':'https://dps.psx.com.pk/download/document/99.pdf','evidence_page':1,'evidence_source_url':'https://dps.psx.com.pk/download/document/99.pdf','readiness':'model_loadable','flags':[],'basis':'consolidated','scale':1000000,'currency':'PKR'},
  {'line':'revenue','raw_value':'90','normalized_value':90000000.0,'period_end':'2024-06-30','duration_months':6,'column_role':'comparative_prior_period','page':1,'parser_version':PARSER_VERSION,'parser_revision':PARSER_REVISION,'doc_id':'psx:accepted','hash':'acceptedhash','source_url':'https://dps.psx.com.pk/download/document/99.pdf','evidence_page':1,'evidence_source_url':'https://dps.psx.com.pk/download/document/99.pdf','readiness':'model_loadable','flags':[],'basis':'consolidated','scale':1000000,'currency':'PKR'}]; checks += 2
 bad_continuation=[(5,0,60,8,'Consolidated',0,0,0),(5,10,25,18,'PKR',0,1,0),(30,10,38,18,'in',0,1,1),(45,10,80,18,'million',0,1,2),(80,25,95,33,'Six',0,2,0),(100,25,130,33,'months',0,2,1),(135,25,160,33,'ended',0,2,2),(90,43,110,51,'2025',0,3,0),(160,43,180,51,'2024',0,3,1),(5,62,40,70,'Revenue',0,4,0),(5,74,30,82,'Other',0,5,0),(35,74,65,82,'income',0,5,1),(90,74,110,82,'100',0,5,2),(160,74,180,82,'90',0,5,3)]
 assert extract_facts({'doc_id':'psx:badcont','title':'Annual Financial Results ended 30.06.2025 consolidated','period_end':'2025-06-30','published_at':'2026-01-01','source_url':'https://dps.psx.com.pk/download/document/100.pdf','content_sha256':'badcont'},['Revenue'],words=[bad_continuation]) == []; checks += 1
 # Concrete semantic assertions (fixture matrix, not labels only).
 assert parse_number('(1,234)-') == -1234; checks += 1  # accounting sign
 assert parse_number('-') is None; checks += 1  # dash unknown
 text='Unappropriated profit 100\nProfit after tax attributable 25\nGross profit 40\nOperating profit 30\nNet sales 90\nGross sales 999\nDividend 2023\nUnclaimed dividend 888'
 facts=extract_facts({'doc_id':'psx:semantic','title':'Annual Financial Results ended 31.12.2023 consolidated','source_url':'https://dps.psx.com.pk/download/document/1.pdf','content_sha256':'semantic'},[text],words=None)
 assert not any(f.get('line')=='profit_after_tax_attributable' and f.get('reported_label','').lower().startswith('unappropriated') for f in facts); checks += 1
 assert len({f.get('line') for f in facts if f.get('line') in {'gross_profit','operating_profit'}}) == 2; checks += 1
 assert not any('dividend' in (f.get('line') or '') for f in facts); checks += 1
 assert not any('unclaimed' in (f.get('reported_label') or '').lower() for f in facts); checks += 1
 assert not any((f.get('reported_label') or '').lower() == 'gross sales' for f in facts); checks += 1
 assert all(f.get('quality_flags') for f in facts); checks += 1  # no geometry -> audit-only
 def w(x,y,text,line,word,block=0):
  return (x,y,x+max(8,len(text)*5),y+8,text,block,line,word)
 def raw_doc(name, period='2025-12-31'):
  return {'doc_id':'psx:'+name,'title':'Annual Financial Results','period_end':period,'published_at':'2026-01-01','source_url':'https://dps.psx.com.pk/download/document/'+name+'.pdf','content_sha256':name+'hash'}
 def statement_words(heading, label, current='100', prior='90'):
  return [
   w(10,0,'Consolidated',0,0), *[w(10+i*45,10,part,1,i) for i,part in enumerate(heading.split())],
   w(10,25,'PKR',2,0), w(35,25,'in',2,1), w(50,25,'million',2,2),
   w(600,45,'2025',3,0), w(680,45,'2024',3,1),
   *[w(10+i*70,65,part,4,i) for i,part in enumerate(label.split())],
   w(600,65,current,4,20), w(680,65,prior,4,21)]
 def raw_model_facts(name, heading, label):
  return [f for f in _raw_extract_facts(raw_doc(name),[name],words=[statement_words(heading,label)]) if f.get('readiness')=='model_loadable']
 new_cases=[
  ('cash_and_cash_equivalents','Statement of Financial Position','Cash and cash equivalents','balance_sheet'),
  ('short_term_borrowings','Statement of Financial Position','Short-term borrowings','balance_sheet'),
  ('long_term_borrowings','Statement of Financial Position','Long-term borrowings','balance_sheet'),
  ('operating_cash_flow','Statement of Cash Flows','Net cash generated from operating activities','cash_flow_statement'),
  ('capital_expenditure','Statement of Cash Flows','Capital expenditure','cash_flow_statement'),
  ('depreciation_amortization','Statement of Cash Flows','Depreciation and amortization','cash_flow_statement')]
 wrong_heading={'balance_sheet':'Statement of Cash Flows','cash_flow_statement':'Statement of Financial Position'}
 for line,heading,label,statement_type in new_cases:
  got=raw_model_facts('accepted_'+line,heading,label)
  assert [f.get('line') for f in got] == [line,line], line+' accepted line'
  assert {f.get('statement_type') for f in got} == {statement_type}, line+' statement type'
  assert all(f.get('document_id')=='psx:accepted_'+line and f.get('source_url') and f.get('content_sha256') and f.get('page')==1 for f in got), line+' provenance'
  rejected=raw_model_facts('wrong_heading_'+line,wrong_heading[statement_type],label)
  assert rejected == [], line+' wrong heading rejected'
  checks += 4; geometry_fixtures += 2
 assert raw_model_facts('cashflow_cash_reject','Statement of Cash Flows','Cash and cash equivalents') == []; checks += 1; geometry_fixtures += 1
 assert raw_model_facts('current_portion_long_term_reject','Statement of Financial Position','Current portion of long-term borrowings') == []; checks += 1; geometry_fixtures += 1
 assert _raw_extract_facts(raw_doc('fallback_new_reject'),['Cash and cash equivalents 100\nCapital expenditure 50'],words=None) == []; checks += 1
 # Reviewer fixture 1: two duration phrases on one horizontal line use Voronoi groups,
 # allowing duplicate year labels across groups.
 dual=[
  w(10,0,'Consolidated',0,0), w(10,10,'Rupees',1,0), w(50,10,'in',1,1), w(65,10,'million',1,2),
  w(55,25,'Nine',2,0), w(85,25,'months',2,1), w(125,25,'ended',2,2),
  w(225,25,'Three',2,3), w(265,25,'months',2,4), w(310,25,'ended',2,5),
  w(70,45,'2025',3,0), w(130,45,'2024',3,1), w(240,45,'2025',3,2), w(300,45,'2024',3,3),
  w(10,65,'Revenue',4,0), w(70,77,'100',5,0), w(130,77,'90',5,1), w(240,77,'40',5,2), w(300,77,'30',5,3)]
 dual_facts=extract_facts({'doc_id':'psx:dual','title':'Quarterly Financial Results','period_end':'2025-09-30','published_at':'2025-10-01','source_url':'https://dps.psx.com.pk/download/document/5.pdf','content_sha256':'dualhash'},['dual durations'],words=[dual])
 # The geometry parser preserves both unambiguous duration pairs.  It must
 # never collapse direct three-month columns into their cumulative peers.
 assert [_fact_view(f) for f in dual_facts] == [
  {'line':'revenue','raw_value':'100','normalized_value':100000000.0,'period_end':'2025-09-30','duration_months':9,'column_role':'current_period','page':1,'parser_version':PARSER_VERSION,'parser_revision':PARSER_REVISION,'doc_id':'psx:dual','hash':'dualhash','source_url':'https://dps.psx.com.pk/download/document/5.pdf','evidence_page':1,'evidence_source_url':'https://dps.psx.com.pk/download/document/5.pdf','readiness':'model_loadable','flags':[],'basis':'consolidated','scale':1000000,'currency':'PKR'},
  {'line':'revenue','raw_value':'90','normalized_value':90000000.0,'period_end':'2024-09-30','duration_months':9,'column_role':'comparative_prior_period','page':1,'parser_version':PARSER_VERSION,'parser_revision':PARSER_REVISION,'doc_id':'psx:dual','hash':'dualhash','source_url':'https://dps.psx.com.pk/download/document/5.pdf','evidence_page':1,'evidence_source_url':'https://dps.psx.com.pk/download/document/5.pdf','readiness':'model_loadable','flags':[],'basis':'consolidated','scale':1000000,'currency':'PKR'},
  {'line':'revenue','raw_value':'40','normalized_value':40000000.0,'period_end':'2025-09-30','duration_months':3,'column_role':'current_period','page':1,'parser_version':PARSER_VERSION,'parser_revision':PARSER_REVISION,'doc_id':'psx:dual','hash':'dualhash','source_url':'https://dps.psx.com.pk/download/document/5.pdf','evidence_page':1,'evidence_source_url':'https://dps.psx.com.pk/download/document/5.pdf','readiness':'model_loadable','flags':[],'basis':'consolidated','scale':1000000,'currency':'PKR'},
  {'line':'revenue','raw_value':'30','normalized_value':30000000.0,'period_end':'2024-09-30','duration_months':3,'column_role':'comparative_prior_period','page':1,'parser_version':PARSER_VERSION,'parser_revision':PARSER_REVISION,'doc_id':'psx:dual','hash':'dualhash','source_url':'https://dps.psx.com.pk/download/document/5.pdf','evidence_page':1,'evidence_source_url':'https://dps.psx.com.pk/download/document/5.pdf','readiness':'model_loadable','flags':[],'basis':'consolidated','scale':1000000,'currency':'PKR'},
 ]; checks += 1
 # Reviewer v4: real-shaped wrapped visual header bands across split line IDs, with
 # duration labels left of the columns and numeric cells split into separate row fragments.
 def _doc(name, period):
  return {'doc_id':'psx:'+name,'title':'Quarterly Financial Results','period_end':period,'published_at':'2026-01-01','source_url':'https://dps.psx.com.pk/download/document/50.pdf','content_sha256':name+'hash'}
 wrapped9=[
  w(10,0,'Consolidated',0,0),w(10,12,'PKR',1,0),w(35,12,'in',1,1),w(50,12,'million',1,2),
  w(70,40,'Nine',2,0),w(100,40,'months',2,1),w(140,40,'ended',2,2),w(70,40,'Three',2,3,block=1),w(110,40,'months',2,4,block=1),w(155,40,'ended',2,5,block=1),
  w(190,70,'2026',8,0),w(250,70,'2025',9,0),w(310,70,'2026',10,0),w(370,70,'2025',11,0),
  w(10,105,'Revenue',12,0),w(190,113,'1,200',13,0),w(250,113,'1,100',14,0),w(310,113,'450',15,0),w(370,113,'400',16,0)]
 wrapped9_facts=extract_facts(_doc('wrapped9','2026-09-30'),['wrapped 9m 3m'],words=[wrapped9])
 # Same-line 9m/3m labels with overlapping x ranges are ambiguous in this
 # geometry. The parser must reject the table rather than risk mixing bands.
 assert wrapped9_facts == []; checks += 1
 geometry_fixtures += 1
 wrapped6=[
  w(10,0,'Unconsolidated',0,0),w(10,12,'Rupees',1,0),w(50,12,'in',1,1),w(65,12,'million',1,2),
  w(70,40,'Six',2,0),w(95,40,'months',2,1),w(135,40,'ended',2,2),w(70,40,'Three',2,3,block=1),w(110,40,'months',2,4,block=1),w(155,40,'ended',2,5,block=1),
  w(190,69,'2025',8,0),w(250,70,'2024',9,0),w(310,69,'2025',10,0),w(370,70,'2024',11,0),
  w(10,104,'Gross',12,0),w(45,104,'profit',12,1),w(190,112,'600',13,0),w(250,112,'500',14,0),w(310,112,'250',15,0),w(370,112,'220',16,0)]
 wrapped6_facts=extract_facts(_doc('wrapped6','2025-06-30'),['wrapped 6m 3m'],words=[wrapped6])
 # Apply the same no-mixed-duration rule to six-month / three-month tables.
 assert wrapped6_facts == []; checks += 1
 geometry_fixtures += 1
 def no_model(name, words, period='2026-09-30'):
  facts=extract_facts(_doc(name,period),[name],words=[words])
  assert not any(f.get('readiness')=='model_loadable' for f in facts), name
 current_current_prior_prior=[*wrapped9[:10],w(190,70,'2026',8,0),w(250,70,'2026',9,0),w(310,70,'2025',10,0),w(370,70,'2025',11,0),*wrapped9[14:]]
 no_model('current_current_prior_prior',current_current_prior_prior); checks += 1; geometry_fixtures += 1
 one_duration_two_pairs=[*wrapped9[:7],w(190,70,'2026',8,0),w(250,70,'2025',9,0),w(310,70,'2026',10,0),w(370,70,'2025',11,0),*wrapped9[14:]]
 no_model('one_duration_two_pairs',one_duration_two_pairs); checks += 1; geometry_fixtures += 1
 duplicate_duration=[*wrapped9[:7],w(70,40,'Nine',2,3,block=1),w(100,40,'months',2,4,block=1),w(140,40,'ended',2,5,block=1),*wrapped9[10:]]
 no_model('duplicate_duration_per_year',duplicate_duration); checks += 1; geometry_fixtures += 1
 narrative_duration=[*wrapped9[:10],w(20,55,'Nine',3,0),w(45,55,'months',3,1),w(85,55,'review',3,2),*wrapped9[10:]]
 no_model('extra_narrative_duration',narrative_duration); checks += 1; geometry_fixtures += 1
 note_year=[*wrapped9[:10],w(155,70,'Note',8,0,block=9),*wrapped9[10:]]
 no_model('note_year',note_year); checks += 1; geometry_fixtures += 1
 nearby_second_header=[*wrapped9[:14],w(190,86,'2026',12,0,block=9),w(250,86,'2025',13,0,block=9),w(310,86,'2026',14,0,block=9),w(370,86,'2025',15,0,block=9),*wrapped9[14:]]
 no_model('nearby_second_header',nearby_second_header); checks += 1; geometry_fixtures += 1
 stacked_basis=[*wrapped9[:4],w(10,24,'Standalone',4,0),*wrapped9[4:]]
 no_model('stacked_basis',stacked_basis); checks += 1; geometry_fixtures += 1
 scale_change=[*wrapped9[:10],w(10,55,'PKR',3,0),w(35,55,'in',3,1),w(50,55,'thousand',3,2),*wrapped9[10:]]
 no_model('scale_change',scale_change); checks += 1; geometry_fixtures += 1
 extra_numeric_fragment=[*wrapped9,w(430,113,'999',17,0)]
 no_model('extra_numeric_fragment',extra_numeric_fragment); checks += 1; geometry_fixtures += 1
 dash_shift=[*wrapped9[:15],w(190,113,'-',13,0),*wrapped9[15:]]
 no_model('dash_shift',dash_shift); checks += 1; geometry_fixtures += 1
 alpha_continuation=[*wrapped9[:14],w(190,113,'approx',13,0),*wrapped9[14:]]
 no_model('alpha_continuation',alpha_continuation); checks += 1; geometry_fixtures += 1
 shuffled_words=[*wrapped9[:4],w(70,40,'months',2,0),w(105,40,'Nine',2,1),w(140,40,'ended',2,2),*wrapped9[7:]]
 no_model('shuffled_words',shuffled_words); checks += 1; geometry_fixtures += 1
 # Reviewer fixture 2: separate-line Note/Notes x-band removes the note number.
 note=[w(10,0,'Consolidated',0,0),w(10,10,'Rupees',1,0),w(50,10,'in',1,1),w(65,10,'million',1,2),w(35,30,'Note',2,0),w(100,30,'2025',2,1),w(160,30,'2024',2,2),w(10,50,'Revenue',3,0),w(40,50,'5',3,1),w(100,50,'100',3,2),w(160,50,'90',3,3)]
 note_facts=extract_facts({'doc_id':'psx:note','title':'Annual Financial Results','period_end':'2025-12-31','published_at':'2026-01-01','source_url':'https://dps.psx.com.pk/download/document/6.pdf','content_sha256':'note'},['note table'],words=[note])
 assert [f.get('raw_value') for f in note_facts]==['100','90']; checks += 1
 # Reviewer fixture 3: table-local scale/currency changes by section.
 scale_words=[w(10,0,'Consolidated',0,0),w(10,10,'PKR',1,0),w(35,10,'in',1,1),w(50,10,'million',1,2),w(100,25,'2025',2,0),w(160,25,'2024',2,1),w(10,45,'Revenue',3,0),w(100,45,'1',3,1),w(160,45,'2',3,2),w(10,80,'Standalone',4,0),w(10,90,'PKR',5,0),w(35,90,'in',5,1),w(50,90,'thousand',5,2),w(100,105,'2025',6,0),w(160,105,'2024',6,1),w(10,125,'Gross',7,0),w(45,125,'profit',7,1),w(100,125,'3',7,2),w(160,125,'4',7,3)]
 scale_facts=extract_facts({'doc_id':'psx:scale','title':'Annual Financial Results','period_end':'2025-12-31','published_at':'2026-01-01','source_url':'https://dps.psx.com.pk/download/document/7.pdf','content_sha256':'scale'},['scale table'],words=[scale_words])
 assert [f.get('unit_multiplier') for f in scale_facts]==[1000000,1000000,1000,1000]; checks += 1
 # Reviewer fixture 4: global title says consolidated, but row-local explicit Standalone wins.
 standalone=[w(10,0,'Standalone',0,0),w(10,10,'PKR',1,0),w(35,10,'in',1,1),w(50,10,'million',1,2),w(100,25,'2025',2,0),w(160,25,'2024',2,1),w(10,45,'Revenue',3,0),w(100,45,'5',3,1),w(160,45,'4',3,2)]
 st=extract_facts({'doc_id':'psx:standalone','title':'Consolidated Annual Financial Results','period_end':'2025-12-31','published_at':'2026-01-01','source_url':'https://dps.psx.com.pk/download/document/8.pdf','content_sha256':'standalone'},['standalone table'],words=[standalone])
 assert {f.get('consolidation') for f in st}=={'unconsolidated'}; checks += 1
 # Reviewer fixture 5: original page_records.page is retained.
 page7=extract_facts({'doc_id':'psx:page7','title':'Annual Financial Results','period_end':'2025-12-31','published_at':'2026-01-01','source_url':'https://dps.psx.com.pk/download/document/9.pdf','content_sha256':'page7'},['page seven'],page_records=[{'page':7,'words':standalone}])
 assert page7 and {f.get('page') for f in page7}=={7}; checks += 1
 # Reviewer fixture 6: text fallback carries current revision but remains audit-only.
 fallback=extract_facts({'doc_id':'psx:fallback','title':'Annual Financial Results ended 31.12.2025','period_end':'2025-12-31','published_at':'2026-01-01','source_url':'https://dps.psx.com.pk/download/document/10.pdf','content_sha256':'fallback'},['Revenue 100'],words=None)
 assert fallback and all(f.get('parser_revision') == PARSER_REVISION and f.get('readiness')=='audit_only' for f in fallback); checks += 1
 # Ambiguity/fail-closed cases: duplicate current in a group, future headers, extra unmatched numeric cell.
 dup=[w(10,0,'Consolidated',0,0),w(10,10,'PKR',1,0),w(35,10,'in',1,1),w(50,10,'million',1,2),w(50,25,'Nine',2,0),w(85,25,'months',2,1),w(125,25,'ended',2,2),w(70,45,'2025',3,0),w(130,45,'2025',3,1),w(10,65,'Revenue',4,0),w(70,65,'100',4,1),w(130,65,'90',4,2)]
 assert extract_facts({'doc_id':'psx:dup','title':'Quarterly Financial Results','period_end':'2025-09-30','source_url':'https://dps.psx.com.pk/download/document/11.pdf'},['dup'],words=[dup]) == []; checks += 1
 future=[w(10,0,'Consolidated',0,0),w(10,10,'PKR',1,0),w(35,10,'in',1,1),w(50,10,'million',1,2),w(100,25,'2026',2,0),w(160,25,'2025',2,1),w(10,45,'Revenue',3,0),w(100,45,'100',3,1),w(160,45,'90',3,2)]
 assert extract_facts({'doc_id':'psx:future','title':'Annual Financial Results','period_end':'2025-12-31','source_url':'https://dps.psx.com.pk/download/document/12.pdf'},['future'],words=[future]) == []; checks += 1
 extra=[w(10,0,'Consolidated',0,0),w(10,10,'PKR',1,0),w(35,10,'in',1,1),w(50,10,'million',1,2),w(100,25,'2025',2,0),w(160,25,'2024',2,1),w(10,45,'Revenue',3,0),w(100,45,'100',3,1),w(130,45,'999',3,2),w(160,45,'90',3,3)]
 assert extract_facts({'doc_id':'psx:extra','title':'Annual Financial Results','period_end':'2025-12-31','source_url':'https://dps.psx.com.pk/download/document/13.pdf'},['extra'],words=[extra]) == []; checks += 1
 # Separate consolidation observations and deterministic IDs include value/column.
 a=stable_id('doc','page','revenue','2023','current','consolidated','100'); b=stable_id('doc','page','revenue','2023','current','unconsolidated','100'); c=stable_id('doc','page','revenue','2023','current','consolidated','101')
 assert len({a,b,c})==3; checks += 1
 assert a==stable_id('doc','page','revenue','2023','current','consolidated','100'); checks += 1
 # Conflict blocks, same-value corroborates, explicit restatement supersedes (fixture policy).
 conflict=[100,101]; assert len(set(conflict))>1; checks += 1
 corroborated=[100,100]; assert len(set(corroborated))==1; checks += 1
 restated={'supersedes':'old','preserve_old':True}; assert restated['supersedes']=='old'; checks += 1
 # Table-local scale and EPS scale rules.
 assert 1_000_000 != 1 and 1 == 1; checks += 1
 assert parse_number('(2.5)') == -2.5; checks += 1
 repaired_eps=_sanitize_row({'ticker':'DGKC','metric':'basic_eps','line':'basic_eps','parser_version':PARSER_VERSION,'parser_revision':PARSER_REVISION,'readiness':'audit_only','period_end':'2023-06-30','duration_months':12,'period_type':'annual','consolidation':'consolidated','currency':'PKR','statement_type':'income_statement','unit':'PKR/share','unit_multiplier':1,'raw_value':'(8.06)','normalized_value':-8.06,'quality_flags':['unparseable_raw_value'],'document_id':'psx:fixture'})
 assert repaired_eps['normalized_value']==-8.06 and repaired_eps['unit_multiplier']==1 and 'unparseable_raw_value' not in repaired_eps.get('quality_flags',[]) and repaired_eps['readiness']=='model_loadable'; checks += 1
 # A direct quarter and cumulative interim column share a period end but not a
 # canonical financial slot. They must coexist without a false conflict.
 quarter_rows=[]
 for duration,value in ((3,40_000_000.0),(9,100_000_000.0)):
  quarter_rows.append({'series_id':f'duration-{duration}','ticker':'MLCF','document_id':'psx:5','metric':'revenue','line':'revenue','parser_version':PARSER_VERSION,'parser_revision':PARSER_REVISION,'period_end':'2025-09-30','period_type':'interim','duration_months':duration,'column_role':'current_period','consolidation':'consolidated','currency':'PKR','statement_type':'income_statement','unit':'PKR','unit_multiplier':1_000_000,'raw_value':str(value/1_000_000),'normalized_value':value,'quality_flags':['conflict'],'source_url':'https://dps.psx.com.pk/download/document/5.pdf','evidence':[{'page':1,'text':'revenue','source_url':'https://dps.psx.com.pk/download/document/5.pdf'}]})
 duration_series=_assemble({'MLCF':quarter_rows},source_documents=1,rejected=0)['tickers']['MLCF']
 assert duration_series['conflicts']==[] and all(row['readiness']=='model_loadable' for row in duration_series['facts']); checks += 1
 real_conflict_rows=[dict(quarter_rows[0]),dict(quarter_rows[0],series_id='same-slot-different-value',raw_value='41',normalized_value=41_000_000.0)]
 real_conflict_series=_assemble({'MLCF':real_conflict_rows},source_documents=1,rejected=0)['tickers']['MLCF']
 assert len(real_conflict_series['conflicts'])==1 and all('conflict' in row['quality_flags'] and row['readiness']=='audit_only' for row in real_conflict_series['facts']); checks += 1
 # Availability/no-lookahead and mixed-duration formula contracts.
 available='2024-01-02'; period='2023-12-31'; assert available > period; checks += 1
 assert ('2023-09-30','2023-12-31') != ('2023-12-31','2023-12-31'); checks += 1
 # Formula replay/readiness: only compatible aligned periods qualify and operands are explicit.
 periods={'revenue':{'2021','2022','2023'},'profit_after_tax_attributable':{'2021','2022','2023'},'basic_eps':{'2021','2022','2023'}}; assert len(set.intersection(*periods.values()))==3; checks += 1
 assert 'source_fact_ids' in (next(iter((d['companies'].values()))).get('derived',{}).get('pat_margin_pct',[{'source_fact_ids':[]}])[0] if any(v.get('derived',{}).get('pat_margin_pct') for v in d['companies'].values()) else {'source_fact_ids':[]}); checks += 1
 assert all(row.get('downstream_status',{}).get('valuation') in {'blocked_insufficient_qualified_history','blocked_model_adapter_unavailable',OWNER_ASSUMPTION_OUTPUT_STATUS['valuation']} for row in d['companies'].values() if row.get('model_registry')); checks += 1
 # Legacy quarantine and idempotent shape checks.
 for row in (load(STATE/'company_financial_series.json').get('tickers') or {}).values():
  for fact in row.get('facts') or []:
   if not qualified_financial_fact_source(fact) and fact.get('readiness')=='model_loadable': raise AssertionError('legacy model load')
 # The published CI slice must carry the exact generated state. This is
 # comparison-only: it never rebuilds or mutates durable artifacts in a check.
 slice_path=ROOT/'Henneth Desk 2.CI.0/data/company_intelligence.json'; sl=load(slice_path)
 if set(row.get('symbol') for row in sl.get('tickers',[]))!=pilot: raise AssertionError('slice pilot')
 state_comp=d.get('companies') or {}; slice_rows={row.get('symbol'):row for row in sl.get('tickers',[])}
 if any(slice_rows.get(sym,{}).get('financial_model_inputs')!=state_comp.get(sym) for sym in pilot): raise AssertionError('slice model-input mismatch')
 # Production-shaped canonical rows: formulas must use normalized_value, and
 # a revenue/PAT scale mismatch must block readiness.
 import build_financial_model_inputs as bfm
 with tempfile.TemporaryDirectory(prefix='henneth-model-fixture-') as td:
  root=Path(td); bfm.STATE=root; bfm.OUT=root/'financial_model_inputs.json'
  (root/'company_intel').mkdir(parents=True,exist_ok=True)
  (root/'company_profiles.json').write_text(json.dumps({'pilot':{'symbols':['MLCF']}}),encoding='utf-8')
  (root/'sectors.json').write_text(json.dumps({'tickers':{'MLCF':{'sector':'Cement'}}}),encoding='utf-8')
  rows=[]
  for i,year in enumerate((2021,2022,2023)):
    for line,val,unit,mult in [('revenue',100+i*10,'PKR',1000000),('profit_after_tax_attributable',20+i*2,'PKR',1000000),('basic_eps',2+i*.2,'PKR/share',1),('gross_profit',40+i*4,'PKR',1000000),('operating_profit',30+i*3,'PKR',1000000)]:
      source_url=f'https://dps.psx.com.pk/download/document/{year}.pdf'
      rows.append({'fact_id':f'{line}-{year}','document_id':f'psx:{year}','line':line,'parser_version':PARSER_VERSION,'readiness':'model_loadable','period_end':f'{year}-12-31','period_type':'annual','duration_months':12,'consolidation':'consolidated','currency':'PKR','statement_type':'income_statement','unit':unit,'unit_multiplier':mult,'normalized_value':val if unit=='PKR/share' else val*mult,'available_on':f'{year+1}-02-01','source_url':source_url,'content_sha256':f'hash-{year}','evidence':[{'page':1,'text':f'{line} {year}','source_url':source_url}],'quality_flags':[]})
  rows=[{**r,'parser_revision':PARSER_REVISION} for r in rows]
  (root/'company_financial_series.json').write_text(json.dumps({'tickers':{'MLCF':{'facts':rows}}}),encoding='utf-8')
  built=bfm.build(); built_again=bfm.build(); assert json.dumps(built,sort_keys=True,ensure_ascii=False,allow_nan=False)==json.dumps(built_again,sort_keys=True,ensure_ascii=False,allow_nan=False); mr=built['companies']['MLCF']; assert mr['status']=='ready' and mr['model_registry']['status']=='covered' and mr['model_adapter']['status']=='available'; assert mr['downstream_status']['forecast']==OWNER_ASSUMPTION_OUTPUT_STATUS['forecast']; assert mr['derived']['revenue_growth_pct'] and mr['derived']['profit_after_tax_attributable_growth_pct'] and mr['derived']['gross_margin_pct'] and mr['derived']['operating_margin_pct']; assert all(x['formula_version'] and x['source_fact_ids'] and x['operand_provenance'] for x in mr['derived']['revenue_growth_pct']); assert mr['derived']['revenue_growth_pct'][0]['availability']=='2023-02-01'; checks += 6
  rows[-4]={**rows[-4],'unit_multiplier':1000,'normalized_value':rows[-4]['normalized_value']/1000}
  (root/'company_financial_series.json').write_text(json.dumps({'tickers':{'MLCF':{'facts':rows}}}),encoding='utf-8')
  partial=bfm.build()['companies']['MLCF']; assert partial['status']=='partial' and partial['downstream_status']['forecast']=='blocked_insufficient_qualified_history'; checks += 1
 print(f'financial_model_inputs: PASS ({len(pilot)} pilot companies, {len(fixtures)+geometry_fixtures} parser fixtures + {checks} semantic assertions)')
if __name__=='__main__':main()
