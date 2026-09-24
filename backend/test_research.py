import copy,io,os,sqlite3,tempfile,unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
from email.message import EmailMessage
from fastapi import HTTPException
from . import research as r

TEXT='\n[Page 1]\nSeptember 20, 2026\nNVIDIA expects improving demand.\n[Page 2]\nRisks include competition.'
REPORT={'title':'NVIDIA update','firm':'Test firm','report_date':'2026-09-20','date_evidence':'September 20, 2026','findings':[{'ticker':'NVDA','summary':'The author expects demand to improve. Competition remains a risk.','stance':'bullish','evidence':'NVIDIA expects improving demand.','page':1,'catalysts':['Demand'],'risks':['Competition']}]}
class ResearchTests(unittest.TestCase):
 def test_mailbox_failure_does_not_block_shared_analysis(self):
  with tempfile.NamedTemporaryFile(suffix='.sqlite',delete=False) as f:path=f.name
  @contextmanager
  def db():
   c=sqlite3.connect(path);c.row_factory=sqlite3.Row
   try:yield c;c.commit()
   finally:c.close()
  try:
   with db() as c:c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
   with patch.object(r,'core',return_value=SimpleNamespace(db=db)),patch.object(r,'import_mail',side_effect=RuntimeError('offline')),patch.object(r,'analyze_one',return_value={'state':'draft_ready'}) as analyze:
    result=r.run('test-token')
    self.assertEqual(result['state'],'mailbox_connection_failed')
    self.assertEqual(result['analysis']['state'],'draft_ready')
    analyze.assert_called_once_with('test-token')
    with db() as c:self.assertEqual(r.meta(c,'lease'),{})
  finally:os.unlink(path)
 def test_import_deduplicates_and_does_not_mark_read(self):
  with tempfile.NamedTemporaryFile(suffix='.sqlite',delete=False) as f:path=f.name
  @contextmanager
  def db():
   c=sqlite3.connect(path);c.row_factory=sqlite3.Row
   try:yield c;c.commit()
   finally:c.close()
  msg=EmailMessage();msg['From']='test@example.com';msg.set_content('')
  msg.add_attachment(b'%PDF-test',maintype='application',subtype='pdf',filename='report.pdf')
  msg.add_attachment(b'%PDF-test',maintype='application',subtype='pdf',filename='duplicate.pdf')
  imap=MagicMock();imap.select.return_value=('OK',[]);imap.response.return_value=('UIDVALIDITY',[b'123'])
  def uid(command,*args):
   if command=='search':return ('OK',[b'1'])
   if args[1]=='(RFC822.SIZE)':return ('OK',[b'1 (RFC822.SIZE 1000)'])
   self.assertEqual(args[1],'(BODY.PEEK[])');return ('OK',[(b'1',msg.as_bytes())])
  imap.uid.side_effect=uid
  try:
   with db() as c:
    r.migrate(c);c.execute('CREATE TABLE stocks(ticker TEXT,name TEXT,active INTEGER)');c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
   with patch.object(r,'core',return_value=SimpleNamespace(db=db)),patch.dict(os.environ,{'RESEARCH_IMAP_PASSWORD':'test'}),patch.object(r.imaplib,'IMAP4_SSL',return_value=imap),patch.object(r,'extract_pdf',return_value=(TEXT,2)):
    self.assertEqual(r.import_mail()['imported'],1)
    self.assertEqual(r.import_mail()['imported'],0)
    with db() as c:
     did=c.execute('SELECT id FROM research_documents').fetchone()[0]
     c.execute("UPDATE research_documents SET status='needs_review'")
     r.put(c,'four_page_retry_enabled',True)
     r.put(c,'four_page_retry:'+did,{'state':'pending'})
    self.assertEqual(r.import_mail()['imported'],1)
    self.assertEqual(r.import_mail()['imported'],0)
    with db() as c:
     self.assertEqual(r.meta(c,'four_page_retry:'+did)['state'],'attempted')
     self.assertEqual(c.execute('SELECT count(*) FROM research_documents').fetchone()[0],1)
    imap.select.assert_called_with('INBOX',readonly=True)
    imap.store.assert_not_called()
  finally:os.unlink(path)
 def test_sector_screen(self):
  text='Pharmaceutical drug trials and hospital services. '*8
  self.assertTrue(r.prescreen('Healthcare Preview.pdf',text,{'NVDA':'NVIDIA Corporation'})['skip'])
  self.assertTrue(r.prescreen('Healthcare.pdf',text+' AI drug discovery and IR team.',{'AI':'C3.ai','IR':'Ingersoll Rand'})['skip'])
  self.assertFalse(r.prescreen('Healthcare.pdf',text+' $AI earnings.',{'AI':'C3.ai'})['skip'])
  self.assertFalse(r.prescreen('Healthcare Preview.pdf',text+' NVIDIA demand.',{'NVDA':'NVIDIA Corporation'})['skip'])
  self.assertFalse(r.prescreen('Healthcare Preview.pdf',text+' TEM earnings.',{'TEM':'Tempus AI, Inc.'})['skip'])
  self.assertFalse(r.prescreen('Mixed market.pdf',text,{'NVDA':'NVIDIA'})['skip'])
  self.assertFalse(r.prescreen('Healthcare.pdf','scanned',{'NVDA':'NVIDIA'})['skip'])
 def test_candidate_hints_require_whole_ticker(self):
  self.assertEqual(r.mentioned_candidates('FLNC (Hold). GOOGLLONG',{'FLNC':'Fluence','GOOGL':'Alphabet'}),{'FLNC':'Fluence'})
 def test_schema_enforces_universe(self):
  schema=r.response_format({'NVDA':'NVIDIA','MU':'Micron'})['json_schema']['schema']
  self.assertEqual(schema['$defs']['Finding']['properties']['ticker']['enum'],['MU','NVDA'])
 def test_valid_evidence(self):
  self.assertEqual(r.validate_report(REPORT,TEXT,{'NVDA'})['findings'][0]['ticker'],'NVDA')
 def test_filename_date_evidence(self):
  value=copy.deepcopy(REPORT);value['report_date']='2026-09-18';value['date_evidence']='9.18.26'
  result=r.validate_report(value,TEXT,{'NVDA'},'Research_9.18.26.pdf')
  self.assertEqual(result['report_date'],'2026-09-18')
 def test_ambiguous_filename_date_rejected(self):
  value=copy.deepcopy(REPORT);value['report_date']='2026-09-10';value['date_evidence']='09.10.26'
  with self.assertRaises(ValueError):r.validate_report(value,TEXT,{'NVDA'},'Research_09.10.26.pdf')
 def test_no_universe_leak(self):
  with self.assertRaises(ValueError):r.validate_report(REPORT,TEXT,{'MU'})
 def test_wrong_page(self):
  value=copy.deepcopy(REPORT);value['findings'][0]['page']=2
  with self.assertRaises(ValueError):r.validate_report(value,TEXT,{'NVDA'})
 def test_pdf_separator_still_requires_exact_words(self):
  value=copy.deepcopy(REPORT);value['findings'][0]['evidence']='NVIDIA'+chr(0)+'expects improving demand.'
  self.assertEqual(r.validate_report(value,TEXT,{'NVDA'})['findings'][0]['evidence'],'NVIDIA expects improving demand.')
 def test_invented_quote(self):
  value=copy.deepcopy(REPORT);value['findings'][0]['evidence']='Guaranteed returns of 100 percent'
  with self.assertRaises(ValueError):r.validate_report(value,TEXT,{'NVDA'})
 def test_duplicate_stock(self):
  value=copy.deepcopy(REPORT);value['findings']*=2
  with self.assertRaises(ValueError):r.validate_report(value,TEXT,{'NVDA'})
 def test_blank_pdf_is_review(self):
  from pypdf import PdfWriter
  w=PdfWriter();w.add_blank_page(width=300,height=300);b=io.BytesIO();w.write(b)
  with self.assertRaisesRegex(ValueError,'OCR'):r.extract_pdf(b.getvalue())
 def test_four_page_limit_and_context(self):
  read=MagicMock(side_effect=lambda i:('NVIDIA expects growth on page '+str(i+1)+'. ')*8)
  text,pages=r.research_excerpt(read,10)
  self.assertEqual(pages,4);self.assertEqual(read.call_count,4)
  self.assertIn('[Page 4]',text);self.assertNotIn('[Page 5]',text)
 def test_disclaimer_stops_before_later_pages(self):
  content=['Demand is improving. '*12,'More useful context. '*12+'\nIMPORTANT DISCLOSURES\nDo not send this legal section.','Must not read.']
  read=MagicMock(side_effect=lambda i:content[i])
  text,pages=r.research_excerpt(read,3)
  self.assertEqual(pages,2);self.assertEqual(read.call_count,2)
  self.assertIn('More useful context',text);self.assertNotIn('legal section',text)
 def test_inline_disclaimer_reference_does_not_stop(self):
  text,pages=r.research_excerpt(lambda i:('Please see disclaimer on page 8. Demand is growing. '*5),2)
  self.assertEqual(pages,2)
 def test_incomplete_page_does_not_poison_remaining_context(self):
  text,pages=r.research_excerpt(lambda i:('Growth continues. '*12+'the next catalyst is') if i==0 else ('a new product. '*12),2)
  self.assertEqual(pages,2);self.assertIn('a new product',text)
 def test_stored_report_stops_at_four(self):
  text=r.limit_stored_excerpt(''.join('\n[Page '+str(i)+']\n'+('Demand is improving. '*12) for i in range(1,7)))
  self.assertIn('[Page 4]',text);self.assertNotIn('[Page 5]',text)
 def test_excerpt_byte_cap(self):
  text,pages=r.research_excerpt(lambda i:('Demand is improving.\n'*2000),4)
  self.assertLessEqual(len(text.encode()),r.MAX_EXCERPT_BYTES)
 def test_page_four_evidence_validates_but_page_five_rejected(self):
  value=copy.deepcopy(REPORT);value['findings'][0]['page']=4
  text=TEXT+'\n[Page 4]\nNVIDIA expects improving demand.'
  self.assertEqual(r.validate_report(value,text,{'NVDA'})['findings'][0]['page'],4)
  value['findings'][0]['page']=5
  with self.assertRaises(ValueError):r.validate_report(value,text,{'NVDA'})
 def test_empty_result_recheck_requires_repeated_explicit_ticker(self):
  text='PALO ALTO NETWORKS (PANW). PANW launches a service. PANW maintains growth. PANW rating Outperform.'
  self.assertEqual(r.empty_result_candidates(text,{'PANW':'Palo Alto Networks'}),['PANW'])
  self.assertEqual(r.empty_result_candidates('Event calendar: PANW.',{'PANW':'Palo Alto Networks'}),[])
  self.assertEqual(r.empty_result_candidates(text,{'MU':'Micron'}),[])
 def test_oversize(self):
  with self.assertRaisesRegex(ValueError,'12 MB'):r.extract_pdf(b'0'*(12*1024*1024+1))
 def test_no_password_no_connect(self):
  with patch.dict(os.environ,{},clear=True),patch.object(r.imaplib,'IMAP4_SSL') as imap:
   self.assertEqual(r.import_mail()['state'],'mailbox_password_required');imap.assert_not_called()
 def test_unauthorized_cron(self):
  with patch.dict(os.environ,{'CRON_SECRET':'test'}):
   with self.assertRaises(HTTPException):r.cron(SimpleNamespace(headers={}))
 def test_member_cannot_read_drafts(self):
  with patch.object(r,'core',return_value=SimpleNamespace(account=lambda req:{'role':'member'})):
   self.assertEqual(r.ticker_research('NVDA',None),{'documents':[]})
 def test_shared_budget_stops_call(self):
  with tempfile.NamedTemporaryFile(suffix='.sqlite',delete=False) as f:path=f.name
  @contextmanager
  def db():
   c=sqlite3.connect(path);c.row_factory=sqlite3.Row
   try:yield c;c.commit()
   finally:c.close()
  try:
   with db() as c:
    r.migrate(c)
    c.execute('CREATE TABLE stocks(ticker TEXT,name TEXT,active INTEGER)')
    c.execute("CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)")
    c.execute('CREATE TABLE ai_sentiment_spend(month TEXT,actual REAL,reserved REAL,cache_key TEXT)')
    c.execute('INSERT INTO ai_sentiment_spend VALUES(?,10,0,?)',(r.datetime.now(r.timezone.utc).strftime('%Y-%m'),'post'))
    c.execute("INSERT INTO research_documents(id,filename,sender,received,text,pages,status,updated) VALUES('x','x.pdf','test',0,?,1,'queued',0)",('[Page 1]\n'+'NVIDIA expects demand to improve. '*6,))
   with patch.object(r,'core',return_value=SimpleNamespace(db=db)),patch.dict(os.environ,{'AI_GATEWAY_API_KEY':'test'}),patch.object(r.httpx,'post') as post:
    self.assertEqual(r.analyze_one()['state'],'budget_paused');post.assert_not_called()
    with db() as c:
     c.execute("INSERT INTO stocks VALUES('NVDA','NVIDIA Corporation',1)")
     c.execute("UPDATE research_documents SET filename='Healthcare Preview.pdf',text=?",('[Page 1]\n'+'Hospital pharmaceutical trials. '*10,))
    self.assertEqual(r.analyze_one()['state'],'screened_out');post.assert_not_called()
  finally:os.unlink(path)

if __name__=='__main__':unittest.main()


def test_structured_target_evidence_and_direction():
 quote='Test firm raises NVIDIA price target to $120 from $100.'
 data=copy.deepcopy(REPORT)
 data['findings'][0]['price_target']=dict(broker='Test firm',currency='USD',current=120,previous=100,evidence=quote,page=2)
 text=TEXT+'\n'+quote
 result=r.validate_report(data,text,{'NVDA'})
 assert result['findings'][0]['price_target']['current']==120
 data['findings'][0]['price_target']['current']=100
 data['findings'][0]['price_target']['previous']=120
 assert r.validate_report(data,text,{'NVDA'})['findings'][0]['price_target'] is None
