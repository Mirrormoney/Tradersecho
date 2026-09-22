# Tradersecho newsletter DNS setup

Provider: United Domains. Zone: tradersecho.com. Resend free plan, EU region.
Sender: newsletter@tradersecho.com. Reply-to/support: info@tradersecho.com.

Add these three records. Names are relative to tradersecho.com. Keep existing root MX/SPF records intact. Do not replace the email hosting setup.

## TXT — resend._domainkey

Value: `p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDGOiV37eYasba0Svydz6YtiAhZgFXSXrmD51Y2w8IUfAN7ii0zHFg+1q2ApPARO3GB+8zZjdxZp4iEYkCEJMiNLQhYsRe9Bd6lLQMkwuyWyTqJEaM5/mupwbmXEDUi5tTBtxqMqFC7RQx5LFNmoOK1U1s8KYNNLtgf5d83tn3TOQIDAQAB`

TTL: provider default

## MX — send

Value: `feedback-smtp.eu-west-1.amazonses.com`
Priority: 10
TTL: provider default

## TXT — send

Value: `v=spf1 include:amazonses.com ~all`

TTL: provider default

After adding all records, trigger Resend verification. No newsletter or X post has been sent.