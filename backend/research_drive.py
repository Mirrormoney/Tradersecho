"""Owner-only Google OAuth and bounded, resumable research-folder ingestion."""
import base64,hashlib,hmac,json,os,re,secrets,time
from datetime import date,datetime,timezone,timedelta
from urllib.parse import urlencode
import httpx
from psycopg import DataError
from pypdf.errors import PdfReadError
from cryptography.fernet import Fernet
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import RedirectResponse
from . import research as research
from .community import core
router=APIRouter()
ROOT='11V-290xs-HF7ifWEJaFT2P1iO0O38Vff'
ROOTS=(ROOT,'1kkJowGz1MWj0GSV-3XKm2bTdTk8uXplz')
CALLBACK='https://tradersecho.com/api/drive/callback'
SCOPE='https://www.googleapis.com/auth/drive.readonly'
API='https://www.googleapis.com/drive/v3/files'
FOLDER='application/vnd.google-apps.folder'
def owner(request):
 u=core().account(request)
 if u.get('demo') or u.get('role')!='owner':raise HTTPException(403,'Owner access required')
 return u
def configured():return bool(os.getenv('GOOGLE_DRIVE_CLIENT_ID') and os.getenv('GOOGLE_DRIVE_CLIENT_SECRET'))
def cipher():
 key=hashlib.sha256(('research-drive:'+os.environ['GOOGLE_DRIVE_CLIENT_SECRET']).encode()).digest()
 return Fernet(base64.urlsafe_b64encode(key))
def get(c,key,default=None):return research.meta(c,'drive_'+key,default)
def put(c,key,value):research.put(c,'drive_'+key,value)
def migrate(c):
 research.migrate(c)
 c.executescript('''CREATE TABLE IF NOT EXISTS research_drive_folders(id TEXT PRIMARY KEY,parent TEXT,page TEXT,checked REAL NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS research_drive_files(id TEXT PRIMARY KEY,parent TEXT,version TEXT NOT NULL,name TEXT NOT NULL,size INTEGER NOT NULL,status TEXT NOT NULL,document_id TEXT,seen REAL NOT NULL,error TEXT);
 CREATE INDEX IF NOT EXISTS drive_pending ON research_drive_files(status,seen);''')
 for root in ROOTS:
  c.execute('INSERT OR IGNORE INTO research_drive_folders(id,parent,checked) VALUES(?,?,?)',(root,'',0))
 if 'modified_at' not in [r['name'] for r in c.execute('PRAGMA table_info(research_drive_files)')]:
  c.execute('ALTER TABLE research_drive_files ADD COLUMN modified_at REAL')
 if not get(c,'file_modified_filter_v1',False):
  # Legacy discovery time is not the file modification time. Recheck metadata before downloading.
  c.execute("UPDATE research_drive_files SET status='awaiting_metadata' WHERE status='pending'")
  c.execute('UPDATE research_drive_folders SET checked=0,page=NULL')
  put(c,'file_modified_filter_v1',True)
 if not get(c,'server_modified_filter_v2',False):
  c.execute("UPDATE research_drive_files SET status='archived_discovery' WHERE status='awaiting_metadata'")
  c.execute('UPDATE research_drive_folders SET checked=0,page=NULL')
  put(c,'server_modified_filter_v2',True)

def production():
 if os.getenv('VERCEL_ENV')!='production':raise HTTPException(403,'Google connection is production-only')
@router.get('/api/admin/drive')
def status(request:Request):
 owner(request)
 with core().db() as c:
  migrate(c)
  counts={r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) n FROM research_drive_files GROUP BY status')}
  cutoff=time.time()-7*86400
  recent={r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) n FROM research_drive_files WHERE modified_at>=? GROUP BY status',(cutoff,))}
  return {'recent_files':recent,'recent_total':sum(recent.values()),'configured':configured(),'enabled':os.getenv('RESEARCH_DRIVE_ENABLED')=='true','publishing_enabled':os.getenv('RESEARCH_DRIVE_PUBLISH_ENABLED')=='true','connected':bool(get(c,'connection')),'worker':get(c,'worker',{}),'files':counts,'root':ROOT,'roots':list(ROOTS),'folder_access':get(c,'folder_access',{})}
@router.post('/api/admin/drive/connect')
def start(request:Request):
 production();u=owner(request)
 if not configured():raise HTTPException(409,'Google OAuth client credentials are not configured')
 state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
 with core().db() as c:
  put(c,'oauth_'+hashlib.sha256(state.encode()).hexdigest(),{'user':u['id'],'until':time.time()+600,'verifier':cipher().encrypt(verifier.encode()).decode()})
 challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
 return {'url':'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({'client_id':os.environ['GOOGLE_DRIVE_CLIENT_ID'],'redirect_uri':CALLBACK,'response_type':'code','scope':SCOPE,'access_type':'offline','prompt':'consent','state':state,'code_challenge':challenge,'code_challenge_method':'S256'})}
@router.get('/api/drive/callback')
def callback(request:Request,state:str='',code:str='',error:str=''):
 production();u=owner(request);key='oauth_'+hashlib.sha256(state.encode()).hexdigest()
 with core().db() as c:
  c.execute('BEGIN IMMEDIATE');pending=get(c,key,{})
  if pending.get('user')!=u['id'] or pending.get('until',0)<time.time():raise HTTPException(400,'Authorization expired; reconnect from Administration')
  put(c,key,{})
 if error or not code:return RedirectResponse('/admin?drive=cancelled',303)
 try:
  r=httpx.post('https://oauth2.googleapis.com/token',data={'client_id':os.environ['GOOGLE_DRIVE_CLIENT_ID'],'client_secret':os.environ['GOOGLE_DRIVE_CLIENT_SECRET'],'code':code,'code_verifier':cipher().decrypt(pending['verifier'].encode()).decode(),'grant_type':'authorization_code','redirect_uri':CALLBACK},timeout=20)
  r.raise_for_status();token=r.json()
  if not token.get('refresh_token') or SCOPE not in token.get('scope','').split():raise ValueError('Missing scope')
  check=httpx.get(API+'/'+ROOT,params={'fields':'id,mimeType','supportsAllDrives':'true'},headers={'Authorization':'Bearer '+token['access_token']},timeout=15)
  check.raise_for_status()
  if check.json().get('mimeType')!=FOLDER:raise ValueError('Folder inaccessible')
  with core().db() as c:
   migrate(c);put(c,'connection',cipher().encrypt(token['refresh_token'].encode()).decode());put(c,'worker',{'state':'connected','at':time.time()})
 except Exception:raise HTTPException(502,'Google connection could not be verified; check folder access and reconnect')
 return RedirectResponse('/admin?drive=connected',303)
def access_token():
 with core().db() as c:encrypted=get(c,'connection')
 if not encrypted:return None
 refresh=cipher().decrypt(encrypted.encode()).decode()
 r=httpx.post('https://oauth2.googleapis.com/token',data={'client_id':os.environ['GOOGLE_DRIVE_CLIENT_ID'],'client_secret':os.environ['GOOGLE_DRIVE_CLIENT_SECRET'],'refresh_token':refresh,'grant_type':'refresh_token'},timeout=20)
 r.raise_for_status();return r.json()['access_token']
def safe_id(value):
 if not re.fullmatch(r'[A-Za-z0-9_-]+',value):raise ValueError('Invalid Drive ID')
 return value

def date_candidates(text):
 # Numeric dates that could be US or European retain both interpretations.
 text=re.sub(r'[_]', ' ', text)
 patterns=[(r'(?<!\d)\d{4}[-.]\d{2}[-.]\d{2}(?!\d)',['%Y-%m-%d']),
           (r'(?<!\d)\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}(?!\d)',['%m-%d-%Y','%d-%m-%Y','%m-%d-%y','%d-%m-%y']),
           (r'\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b',['%d %B %Y','%d %b %Y']),
           (r'\b[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}\b',['%B %d %Y','%b %d %Y'])]
 found=set()
 for pattern,formats in patterns:
  for candidate in re.findall(pattern,text):
   candidate=candidate.replace(',','')
   if re.match(r'^\d+[./-]\d',candidate):candidate=re.sub(r'[./]','-',candidate)
   for fmt in formats:
    try:found.add(datetime.strptime(candidate,fmt).date())
    except ValueError:pass
 return found

def first_page(text):return re.split(r'\n\[Page 2\]',text,maxsplit=1)[0]

def recent_date_candidate(text,today=None,filename=''):
 today=today or datetime.now(timezone.utc).date()
 return any(today-timedelta(days=30)<=d<=today for d in date_candidates(filename+'\n'+first_page(text)))

def date_screen(text,filename):
 dates=date_candidates(filename+'\n'+first_page(text))
 # Unknown formats go to AI; explicit older dates save unnecessary archive work.
 return not dates or recent_date_candidate(text,filename=filename)

def under_root(client,fid,deadline=None):
 # Recheck current ancestry before downloading. No shortcuts or out-of-root traversal.
 visited=set();pending=[safe_id(fid)]
 for _ in range(24):
  if deadline is not None and time.monotonic()>deadline:raise TimeoutError('Drive check deadline')
  if not pending:return False
  current=pending.pop()
  if current in ROOTS:return True
  if current in visited:continue
  visited.add(current)
  r=client.get(API+'/'+current,params={'fields':'parents,trashed','supportsAllDrives':'true'});r.raise_for_status();d=r.json()
  if not d.get('trashed'):pending.extend(d.get('parents',[]))
 return False
def discovery_query(folder_id,now=None):
 cutoff=datetime.fromtimestamp((time.time() if now is None else now)-7*86400,timezone.utc).isoformat().replace('+00:00','Z')
 # Date applies only to PDFs: old folders may contain newly modified notes.
 return "'"+safe_id(folder_id)+"' in parents and trashed=false and (mimeType='"+FOLDER+"' or (mimeType='application/pdf' and modifiedTime >= '"+cutoff+"'))"

def scan(client,deadline):
 with core().db() as c:
  folders=[dict(r) for r in c.execute('SELECT * FROM research_drive_folders WHERE checked<? ORDER BY checked,id LIMIT 80',(time.time()-900,))]
 for folder in folders:
  if time.monotonic()>deadline:break
  try:
   if not under_root(client,folder['id'],deadline):
    with core().db() as c:c.execute('UPDATE research_drive_folders SET checked=? WHERE id=?',(time.time(),folder['id']))
    continue
   params={'q':discovery_query(folder['id']),'fields':'nextPageToken,files(id,name,mimeType,size,modifiedTime,md5Checksum)','pageSize':100,'orderBy':'modifiedTime desc','supportsAllDrives':'true','includeItemsFromAllDrives':'true'}
   if folder['page']:params['pageToken']=folder['page']
   r=client.get(API,params=params)
   if folder['id'] in ROOTS:
    with core().db() as c:
     access=get(c,'folder_access',{});access[folder['id']]={'status':r.status_code,'at':time.time()};put(c,'folder_access',access)
   if r.status_code in (403,404):
    with core().db() as c:c.execute('UPDATE research_drive_folders SET checked=? WHERE id=?',(time.time(),folder['id']))
    continue
   if r.status_code==400 and folder['page']:
    # Expired/invalid listing cursors must not block the other folders.
    with core().db() as c:c.execute('UPDATE research_drive_folders SET page=NULL,checked=? WHERE id=?',(time.time(),folder['id']))
    continue
   r.raise_for_status();payload=r.json()
   with core().db() as c:
    for f in payload.get('files',[]):
     if f['mimeType']==FOLDER:
      c.execute('INSERT OR IGNORE INTO research_drive_folders(id,parent,checked) VALUES(?,?,?)',(f['id'],folder['id'],0));continue
     version=f.get('md5Checksum') or f.get('modifiedTime','')
     modified=file_modified_at(f.get('modifiedTime'))
     old=c.execute('SELECT version,status,document_id,error FROM research_drive_files WHERE id=?',(f['id'],)).fetchone()
     size=int(f.get('size') or 0)
     same=bool(old and old['version']==version)
     retained=same and old['status'] not in ('pending','awaiting_metadata','archived_discovery','outside_modified_window')
     if retained:state=old['status']
     elif modified is None:state='needs_review'
     elif modified<time.time()-7*86400:state='outside_modified_window'
     else:state='pending' if 0<size<=12*1024*1024 else 'needs_review'
     reason=(old['error'] if retained else 'Missing or invalid PDF modifiedTime' if modified is None else 'PDF size requires review' if state=='needs_review' else None)
     c.execute('INSERT INTO research_drive_files(id,parent,version,name,size,status,seen,modified_at,document_id,error) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET parent=excluded.parent,version=excluded.version,name=excluded.name,size=excluded.size,status=excluded.status,document_id=excluded.document_id,error=excluded.error,seen=excluded.seen,modified_at=excluded.modified_at',(f['id'],folder['id'],version,f['name'][:200],size,state,time.time(),modified,old['document_id'] if retained else None,reason))
    page=payload.get('nextPageToken')
    c.execute('UPDATE research_drive_folders SET page=?,checked=? WHERE id=?',(page,0 if page else time.time(),folder['id']))
  except TimeoutError:break
  except (httpx.HTTPStatusError,httpx.TransportError) as exc:
   if isinstance(exc,httpx.HTTPStatusError) and exc.response.status_code==401:raise
   # Defer only this folder; oldest-first ordering gives the others a turn.
   with core().db() as c:
    c.execute('UPDATE research_drive_folders SET checked=? WHERE id=?',(time.time(),folder['id']))
    put(c,'last_folder_failure',{'at':time.time(),'error_type':type(exc).__name__,'status':exc.response.status_code if isinstance(exc,httpx.HTTPStatusError) else None})

def file_modified_at(value):
 try:
  stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
  return stamp.timestamp() if stamp.tzinfo else None
 except (AttributeError,TypeError,ValueError):return None

def pending_priority(f):
 today=datetime.now(timezone.utc).date()
 dates=date_candidates(f['name'])
 recent=[d for d in dates if today-timedelta(days=30)<=d<=today]
 # Use filename dates only to prioritize. Publication still requires validated evidence.
 return (0 if recent else (1 if not dates else 2),-max(recent).toordinal() if recent else 0,-f['seen'],f['id'])

def import_files(client,deadline):
 with core().db() as c:
  cutoff=time.time()-7*86400
  c.execute("UPDATE research_drive_files SET status='outside_modified_window' WHERE status='pending' AND modified_at<?",(cutoff,))
  rows=[dict(r) for r in c.execute("SELECT * FROM research_drive_files WHERE status='pending' AND modified_at>=? ORDER BY modified_at DESC,id LIMIT 5000",(cutoff,))]
 rows=sorted(rows,key=pending_priority)[:8]
 for f in rows:
  if time.monotonic()>deadline:break
  try:
   if not under_root(client,f['id'],deadline):
    with core().db() as c:c.execute("UPDATE research_drive_files SET status='outside_folder' WHERE id=?",(f['id'],))
    continue
   raw=bytearray()
   with client.stream('GET',API+'/'+safe_id(f['id']),params={'alt':'media'}) as r:
    r.raise_for_status()
    for chunk in r.iter_bytes():
     if time.monotonic()>deadline:raise TimeoutError('Drive download deadline')
     raw.extend(chunk)
     if len(raw)>12*1024*1024:raise ValueError('Oversize PDF')
   did=hashlib.sha256(raw).hexdigest()
   with core().db() as c:
    exists=c.execute('SELECT id FROM research_documents WHERE id=?',(did,)).fetchone()
    recovering=research.claim_recovery(c,did) if exists else False
   if not exists or recovering:
    try:text,pages=research.extract_pdf(bytes(raw))
    except Exception as exc:
     # Malformed PDF internals must not poison every later batch. No source text in diagnostics.
     with core().db() as c:
      reason=str(exc)[:240] if isinstance(exc,ValueError) else 'PDF parsing failed; manual extraction review required'
      c.execute("UPDATE research_drive_files SET status='needs_review',error=? WHERE id=?",(reason,f['id']))
      if recovering:research.save_recovered(c,did,'',0,'needs_review',str(exc) if isinstance(exc,ValueError) else 'PDF parsing failed; manual review required')
     continue
    with core().db() as c:catalog={r['ticker']:r['name'] for r in c.execute('SELECT ticker,name FROM stocks WHERE active=1')}
    screening=research.prescreen(f['name'],text,catalog)
    # Every note passes the existing universe screen; AI/date validation is separate.
    state='screened_out' if screening['skip'] else ('queued' if date_screen(text,f['name']) else 'needs_review')
    reason='No recent date candidate in filename or first page; review before spending AI tokens' if state=='needs_review' else None
    with core().db() as c:
     c.execute('INSERT OR IGNORE INTO research_documents(id,filename,sender,received,text,pages,status,error,updated) VALUES(?,?,?,?,?,?,?,?,?)',(did,f['name'],'Google Drive research',time.time(),text,pages,state,reason,time.time()))
     if recovering:research.save_recovered(c,did,text,pages,state,reason)
   with core().db() as c:c.execute("UPDATE research_drive_files SET status=?,document_id=? WHERE id=?",('duplicate' if exists else 'imported',did,f['id']))
  except DataError:
   # The failed document transaction has rolled back. Quarantine only this file;
   # connection/infrastructure errors still bubble up for a worker alert.
   with core().db() as c:c.execute("UPDATE research_drive_files SET status='needs_review',error='Invalid document data; skipped without blocking later files' WHERE id=?",(f['id'],))
  except httpx.HTTPStatusError as e:
   if e.response.status_code in (429,500,502,503,504):raise
   with core().db() as c:c.execute("UPDATE research_drive_files SET status='needs_review',error='Download unavailable; check permissions' WHERE id=?",(f['id'],))
  except (ValueError,PdfReadError,NotImplementedError):
   with core().db() as c:c.execute("UPDATE research_drive_files SET status='needs_review',error='PDF extraction or size requires review' WHERE id=?",(f['id'],))
  finally:
   with core().db() as c:
    state=c.execute('SELECT status FROM research_drive_files WHERE id=?',(f['id'],)).fetchone()
    if state and state[0]!='pending':put(c,'last_progress',time.time())
def publish_validated():
 from .research_feed import migrate as pub_migrate
 cutoff=(datetime.now(timezone.utc).date()-timedelta(days=30)).isoformat()
 with core().db() as c:
  pub_migrate(c)
  rows=c.execute("SELECT d.id,d.result FROM research_documents d WHERE d.status='draft' AND NOT EXISTS (SELECT 1 FROM research_publications p WHERE p.document_id=d.id) ORDER BY d.updated").fetchall()
  for row in rows:
   try:
    result=json.loads(row['result'])
    if not isinstance(result,dict):raise ValueError('Invalid publication record')
    if not isinstance(result.get('findings'),list):raise ValueError('Invalid findings')
    if result.get('report_date') is not None and not isinstance(result['report_date'],str):raise ValueError('Invalid report date')
    if any(not isinstance(f,dict) or not isinstance(f.get('ticker'),str) for f in result['findings']):raise ValueError('Invalid ticker link')
   except (ValueError,TypeError):
    c.execute("UPDATE research_documents SET status='needs_review',error='Invalid publication record',updated=? WHERE id=?",(time.time(),row['id']))
    continue
   if result.get('report_date') and cutoff<=result['report_date']<=date.today().isoformat() and result.get('date_evidence') and result.get('findings'):
    for f in result['findings']:c.execute('INSERT OR IGNORE INTO research_links VALUES(?,?)',(row['id'],f['ticker']))
    c.execute('INSERT OR IGNORE INTO research_publications VALUES(?,?)',(row['id'],time.time()))
def run():
 if os.getenv('VERCEL_ENV')!='production' or os.getenv('RESEARCH_DRIVE_ENABLED')!='true':return {'state':'disabled'}
 if not configured():return {'state':'credentials_required'}
 lease=secrets.token_hex(16)
 with core().db() as c:
  migrate(c);c.execute('BEGIN IMMEDIATE')
  if get(c,'lease',{}).get('until',0)>time.time():return {'state':'busy'}
  put(c,'lease',{'token':lease,'until':time.time()+300})
 stage='authentication'
 try:
  token=access_token()
  if not token:result={'state':'connection_required'}
  else:
   stage='publication'
   if os.getenv('RESEARCH_DRIVE_PUBLISH_ENABLED')=='true':publish_validated()
   with httpx.Client(headers={'Authorization':'Bearer '+token},timeout=20,follow_redirects=False) as client:
    deadline=time.monotonic()+150
    stage='scan';scan(client,min(deadline,time.monotonic()+55))
    stage='import';import_files(client,deadline)
   if os.getenv('RESEARCH_DRIVE_PUBLISH_ENABLED')=='true':publish_validated()
   result={'state':'ok'}
 except TimeoutError:result={'state':'batch_yielded'}
 except httpx.HTTPStatusError as e:
  try:
   detail=e.response.json().get('error',{})
   reason=detail if isinstance(detail,str) else (detail.get('errors') or [{}])[0].get('reason','unknown')
  except Exception:reason='unknown'
  result={'state':'reconnect_required' if stage=='authentication' and e.response.status_code in (400,401) else 'provider_error','stage':stage,'http_status':e.response.status_code,'reason':str(reason)[:80]}
 except Exception as exc:result={'state':'needs_review','stage':stage,'error_type':type(exc).__name__}
 finally:
  with core().db() as c:
   if get(c,'lease',{}).get('token')==lease:put(c,'lease',{})
 with core().db() as c:put(c,'worker',{**result,'at':time.time()})
 return result
@router.get('/api/cron/drive')
def cron(request:Request):
 secret=os.getenv('CRON_SECRET','')
 if not secret or not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+secret):raise HTTPException(401,'Unauthorized')
 return run()
