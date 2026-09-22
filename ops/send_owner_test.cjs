// Operator-only one-time send. Requires a reviewed prepared payload and explicit --send.
// Persist the attempt BEFORE sending; retries reuse identical content and key.
const fs = require('node:fs');
const crypto = require('node:crypto');
async function main() {
  const [payloadPath, receiptPath, action] = process.argv.slice(2);
  if (!payloadPath || !receiptPath || action !== '--send') throw new Error('Usage: payload.json receipt.json --send');
  const body = fs.readFileSync(payloadPath, 'utf8');
  const payload = JSON.parse(body);
  if (payload.to?.length !== 1 || !payload.subject.startsWith('[Test]') || payload.from !== 'Tradersecho <newsletter@tradersecho.com>') throw new Error('Owner test payload required');
  if (!process.env.RESEND_API_KEY) throw new Error('Missing server-side Resend credential');
  const hash = crypto.createHash('sha256').update(body).digest('hex');
  let receipt;
  if (fs.existsSync(receiptPath)) {
    receipt = JSON.parse(fs.readFileSync(receiptPath,'utf8'));
    if (receipt.hash !== hash) throw new Error('Payload changed: do not retry');
    if (receipt.id) {console.log(JSON.stringify({id:receipt.id,status:'already_sent'}));return;}
    if (Date.now()-receipt.started > 23*3600000) throw new Error('Attempt expired: reconcile with provider before any new send');
  } else {
    receipt = {hash,key:'owner-test-'+crypto.randomUUID(),started:Date.now(),status:'pending'};
    fs.writeFileSync(receiptPath,JSON.stringify(receipt),{flag:'wx'});
  }
  const r = await fetch('https://api.resend.com/emails', {method:'POST',
    headers:{Authorization:'Bearer '+process.env.RESEND_API_KEY,'Content-Type':'application/json','Idempotency-Key':receipt.key},body,signal:AbortSignal.timeout(30000)});
  const data=await r.json();
  if (!r.ok || !data.id) throw new Error('Provider rejected send: '+r.status+' '+JSON.stringify(data));
  receipt.id=data.id;receipt.status='accepted';
  fs.writeFileSync(receiptPath,JSON.stringify(receipt));
  console.log(JSON.stringify({id:data.id,status:'accepted'}));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
