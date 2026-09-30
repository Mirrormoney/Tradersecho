"""Research pipeline health checks; aggregate diagnostics only."""
import json,os
from datetime import datetime,timezone,timedelta

def snapshot(c,now):
 issues=[]
 for key,label,max_age in [('research_worker','Email / analysis worker',25*60),('research_drive_worker','Google Drive worker',60*60)]:
  row=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
  worker=json.loads(row[0]) if row else {}
  if not worker.get('at') or now-worker['at']>max_age:issues.append(label+' heartbeat is overdue.')
  elif worker.get('state') not in ('ok','batch_yielded'):
   detail=' / '.join(str(worker[k]) for k in ('stage','error_type','reason') if worker.get(k))
   issues.append(label+' reports '+str(worker.get('state','unknown'))+(' ('+detail+')' if detail else '')+'.')
  if worker.get('analysis',{}).get('state') in ('budget_paused','ai_credentials_required','worker_error'):issues.append('Research analysis reports '+worker['analysis']['state']+'.')
  if worker.get('image_state'):issues.append(worker['image_state']+'.')
 rows=c.execute('SELECT status,COUNT(*) n,MIN(updated) oldest FROM research_documents GROUP BY status').fetchall()
 counts={r['status']:r['n'] for r in rows}
 last_completed=c.execute("SELECT MAX(updated) FROM research_documents WHERE status IN ('draft','no_match','needs_review','screened_out')").fetchone()[0]
 for r in rows:
  if r['status'] in ('queued','awaiting_analysis') and now-r['oldest']>2*3600 and (not last_completed or now-last_completed>30*60 or now-r['oldest']>86400):issues.append(f"{r['n']} notes are {r['status'].replace('_',' ')}; the oldest has waited over two hours.")
  if r['status']=='analyzing' and now-r['oldest']>15*60:issues.append('An analysis has not finished after 15 minutes.')
 # Observe the Drive queue separately: it exists before research_documents.
 from . import research
 tables=[r['name'] for r in c.execute('PRAGMA table_info(research_drive_files)')]
 if 'status' in tables:
  pending=c.execute("SELECT COUNT(*) FROM research_drive_files WHERE status='pending'").fetchone()[0]
  observed=research.meta(c,'drive_pending_observed',0)
  if pending:
   if not observed:observed=now;research.put(c,'drive_pending_observed',now)
   progressed=research.meta(c,'drive_last_progress',0)
   if now-max(observed,progressed)>3600:issues.append('Google Drive pending PDFs have made no import progress for over one hour.')
  elif observed:research.put(c,'drive_pending_observed',0)
 # A healthy heartbeat is insufficient when analyses fail or publication stalls.
 recent_failures=c.execute("SELECT COUNT(*) FROM research_documents WHERE status='needs_review' AND updated>? AND (error LIKE '%Evidence%' OR error LIKE '%AI response%' OR error LIKE '%Incomplete analysis%' OR error='Invalid publication record')",(now-3600,)).fetchone()[0]
 if recent_failures>=3:issues.append('Repeated research validation failures: '+str(recent_failures)+' notes held in the past hour; automatic source validation could not recover them.')
 if os.getenv('RESEARCH_DRIVE_PUBLISH_ENABLED')=='true' and c.execute('PRAGMA table_info(research_publications)').fetchall():
  cutoff=(datetime.fromtimestamp(now,timezone.utc).date()-timedelta(days=30)).isoformat()
  waiting=0
  for r in c.execute("SELECT d.result FROM research_documents d WHERE d.status='draft' AND d.updated<? AND NOT EXISTS (SELECT 1 FROM research_publications p WHERE p.document_id=d.id)",(now-1800,)):
   try:
    v=json.loads(r['result'])
    if isinstance(v,dict) and isinstance(v.get('report_date'),str) and cutoff<=v['report_date']<=datetime.fromtimestamp(now,timezone.utc).date().isoformat() and v.get('findings') and v.get('date_evidence'):waiting+=1
   except (ValueError,TypeError):waiting+=1
  if waiting:issues.append(str(waiting)+' validated research notes have not reached publication after 30 minutes.')
 operational_issues=list(issues)
 review=c.execute("SELECT COUNT(*) FROM research_documents WHERE status='needs_review' AND updated>?",(now-86400,)).fetchone()[0]
 if review:issues.append(f'{review} notes entered manual review in the past 24 hours. They have not been automatically published.')
 mail_review=c.execute("SELECT COUNT(*) FROM research_messages WHERE status IN ('oversize_or_unavailable','fetch_needs_review','parse_needs_review') AND updated>?",(now-86400,)).fetchone()[0]
 if mail_review:issues.append(f'{mail_review} email messages were skipped for size, fetching or parsing problems; later messages continue.')
 recent={r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) n FROM research_documents WHERE updated>? GROUP BY status',(now-86400,))}
 reasons=[{'reason':r['error'] or 'Unspecified review reason','count':r['n']} for r in c.execute("SELECT error,COUNT(*) n FROM research_documents WHERE status='needs_review' AND updated>? GROUP BY error",(now-86400,))]
 return {'issues':issues,'operational_issues':operational_issues,'review_reasons':reasons,'recent':recent,'counts':counts,'checked_at':now}
