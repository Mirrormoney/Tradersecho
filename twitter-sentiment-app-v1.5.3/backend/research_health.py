"""Research pipeline health checks; aggregate diagnostics only."""
import json

def snapshot(c,now):
 issues=[]
 for key,label,max_age in [('research_worker','Email / analysis worker',25*60),('research_drive_worker','Google Drive worker',60*60)]:
  row=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
  worker=json.loads(row[0]) if row else {}
  if not worker.get('at') or now-worker['at']>max_age:issues.append(label+' heartbeat is overdue.')
  elif worker.get('state') not in ('ok','batch_yielded'):issues.append(label+' reports '+str(worker.get('state','unknown'))+'.')
  if worker.get('analysis',{}).get('state') in ('budget_paused','ai_credentials_required','worker_error'):issues.append('Research analysis reports '+worker['analysis']['state']+'.')
 rows=c.execute('SELECT status,COUNT(*) n,MIN(updated) oldest FROM research_documents GROUP BY status').fetchall()
 counts={r['status']:r['n'] for r in rows}
 for r in rows:
  if r['status'] in ('queued','awaiting_analysis') and now-r['oldest']>2*3600:issues.append(f"{r['n']} notes are {r['status'].replace('_',' ')}; the oldest has waited over two hours.")
  if r['status']=='analyzing' and now-r['oldest']>15*60:issues.append('An analysis has not finished after 15 minutes.')
 review=c.execute("SELECT COUNT(*) FROM research_documents WHERE status='needs_review' AND updated>?",(now-86400,)).fetchone()[0]
 if review:issues.append(f'{review} notes entered manual review in the past 24 hours. They have not been automatically published.')
 mail_review=c.execute("SELECT COUNT(*) FROM research_messages WHERE status!='imported' AND updated>?",(now-86400,)).fetchone()[0]
 if mail_review:issues.append(f'{mail_review} email messages were skipped for size, fetching or parsing problems; later messages continue.')
 return {'issues':issues,'counts':counts,'checked_at':now}
