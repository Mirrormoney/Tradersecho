# Tradersecho payments

## Prices and entitlements

Free: $0. Premium: $19 monthly or $190 annually (two months free / 16.67% savings, not 20%). Founder: $999 once, Premium features for the operating lifetime of the active service. Founder retains the same usage limits as Premium, including five personal voices. Existing owners/admins retain their access and cannot accidentally buy another membership.

Founder is recorded in `billing_entitlements`; the existing `accounts.plan=premium` is the effective access level. A cancellation of another subscription cannot remove an active Founder entitlement. A full Founder refund or disputed charge removes its entitlement; partial refunds do not. Subscription access requires current Stripe status active/trialing; past-due subscriptions lose access until recovery. Cancellation scheduled at period end retains access until Stripe marks it cancelled.

## Current deployment status

Stripe Marketplace sandbox `stripe-cordovan-jacket` is connected to the Vercel project. Three USD tax-inclusive sandbox prices and a billing portal (invoices, payment methods, cancellation at period end) were provisioned. `BILLING_ENABLED=false` in Preview. No live payments or hosted webhook delivery are enabled. The protected preview remains private. Sandbox purchases were verified against an isolated local SQLite database, never against real member accounts.

## Before opening checkout

1. Owner claims the sandbox from the Stripe resource in Vercel and completes Stripe business/bank onboarding privately. Obtain live credentials only through secure environment settings.
2. Confirm seller details, VAT/tax obligations, consumer cancellation/refund terms and Founder terms before selling. Current sandbox prices are tax-inclusive; reproduce that intentionally for live prices. Stripe Tax is optional (`STRIPE_AUTOMATIC_TAX=true`) and requires correct tax registration/product configuration; Stripe Payments alone is not a merchant-of-record tax-remittance service.
3. Create matching live USD prices and set server-only `STRIPE_SECRET_KEY`, `STRIPE_PRICE_MONTHLY`, `STRIPE_PRICE_YEARLY`, `STRIPE_PRICE_FOUNDER`. The server validates amount, currency and billing interval before checkout.
4. Set canonical `APP_ORIGIN`. Configure the Stripe customer portal in the matching Stripe environment with invoice history, payment methods and cancellation at period end. Subscription price switching is not enabled yet; the portal is cancellation/maintenance only. Existing subscribers should not buy Founder while another subscription is active.
5. Register `/api/billing/webhook` with Stripe and set `STRIPE_WEBHOOK_SECRET`. Events: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `charge.refunded`, `charge.dispute.created`, `charge.dispute.closed`. Stripe signature verification is mandatory. Do not weaken whole-site preview protection just to receive webhooks: use a deliberately configured reachable webhook endpoint at launch or a scoped approved test-delivery path.
6. Verify hosted Stripe webhook delivery, replay, renewal failure/recovery, cancellation, full Founder refund and the customer portal using isolated test accounts. Test Apple Pay on a supported device/wallet. Card wallets are supported by hosted Checkout; eligibility depends on browser, device and Stripe settings.
7. Set `BILLING_ENABLED=true` only in the intended environment and redeploy after those checks. Sandbox keys must not unlock real paid memberships. Configure Stripe webhook failure alerts and reconcile billing discrepancies before opening broadly.

## Implementation and checks

`backend/payments.py`: server-selected prices, authenticated account/customer mapping, reusable open Checkout sessions, expiration on tier changes, idempotency keys, Stripe-hosted portal, signed and deduplicated events, canonical provider status retrieval under the database lock. Checkout return URLs only refresh membership; they cannot grant access.

`billing_checkouts` stores account-bound checkout sessions; `billing_entitlements` stores subscription/Founder access. Existing `webhook_events` deduplicates deliveries. New tables are created by the normal application migration. No card data enters Tradersecho.

Verified: 26 backend tests, frontend production build, desktop/mobile comparison and interval switch; real sandbox Checkout creation for all three tiers, monthly/yearly payments and cancellations, Founder payment and full refund, test-customer cleanup. End-to-end hosted webhook delivery is pending the reachable endpoint configuration described above.
