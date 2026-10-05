const key = 'te_campaign_signup'
const allowed = new Set(['signal_audience_test_oct2026', 'ai_insights_feature_test_oct2026'])
const privateVisit = () => navigator.doNotTrack === '1' || navigator.globalPrivacyControl === true

export function captureCampaign() {
 try {
  if (privateVisit()) { sessionStorage.removeItem(key); return }
  const p = new URLSearchParams(location.search)
  if (p.get('utm_source') !== 'x' || p.get('utm_medium') !== 'paid_social' || !allowed.has(p.get('utm_campaign'))) return
  const content = p.get('utm_content') || ''
  if (!/^[A-Za-z0-9_-]{0,80}$/.test(content)) return
  sessionStorage.setItem(key, JSON.stringify({source:'x',medium:'paid_social',campaign:p.get('utm_campaign'),content,at:Date.now()}))
 } catch { /* Blocked storage must never prevent signup. */ }
}
export function campaignForSignup() {
 try {
  if (privateVisit()) { sessionStorage.removeItem(key); return undefined }
  const value = JSON.parse(sessionStorage.getItem(key) || 'null')
  if (!value || !allowed.has(value.campaign) || !Number.isFinite(value.at) || Date.now()-value.at > 7*86400000 || value.at > Date.now()) return undefined
  return value
 } catch { return undefined }
}
