# Tradersecho payments

## Prices and entitlements

Free: $0. Premium: $19 monthly or $190 annually (two months free / 16.67% savings, not 20%). Founder: $999 once, Premium features for the operating lifetime of the active service. Founder retains the same usage limits as Premium, including five personal voices. Existing owners/admins retain their access and cannot accidentally buy another membership.

Founder is recorded in `billing_entitlements`; the existing `accounts.plan=premium` is the effective access level. A cancellation of another subscription cannot remove an active Founder entitlement. A full Founder refund or unresolved/lost disputed charge removes its entitlement; partial refunds do not. Won/closed disputes restore access only if the charge has not been fully refunded. Subscription access requires current Stripe status active/trialing; past-due subscriptions lose access until recovery. Cancellation scheduled at period end retains access until Stripe marks it cancelled.

## Current deployment status

Stripe Marketplace sandbox `stripe-cordovan-jacket` is connected and accessible after the owner claim. The dedicated protected payment test site is https://tradersecho-payments-sandbox-sven-mais-projects.vercel.app/ and uses PostgreSQL schema `billing_sandbox_v1`. It has `BILLING_SANDBOX=true` and `BILLING_ENABLED=true`, no X or Resend token, and its own account/session rows. Normal Tradersecho Preview remains on its original schema with `BILLING_ENABLED=false`.

Three USD tax-inclusive sandbox prices, the billing portal and a signed Stripe webhook are configured. Stripe delivers directly to the protected sandbox using Vercel's supported automation bypass query parameter. That URL contains a credential: keep it inside Stripe configuration, never in source/docs/screenshots. The signing secret is a deployment-only environment override, not a main Preview variable.

Test keys are rejected unless both sandbox mode and a `billing_sandbox_` database schema are explicitly selected. Live keys are rejected in sandbox mode. This prevents accidentally granting real accounts access through test purchases.

The prior Preview was missing the new billing tables; those were applied additively without member-plan changes. Health checks now verify the billing tables as well as database connectivity. **Before deploying future schema changes, run `python -m backend.migrate` with the intended database/schema configured and `DEMO_ENABLED=false`, then verify `/api/health`. Vercel requests do not automatically run migrations.**

## Before opening checkout

1. Owner completes Stripe business/bank onboarding privately for a live account. Obtain live credentials only through secure environment settings.
2. Confirm seller details, VAT/tax obligations, consumer cancellation/refund terms and Founder terms before selling. Current sandbox prices are tax-inclusive; reproduce that intentionally for live prices. Stripe Tax is optional (`STRIPE_AUTOMATIC_TAX=true`) and requires correct tax registration/product configuration; Stripe Payments alone is not a merchant-of-record tax-remittance service.
3. Create matching live USD prices and set server-only `STRIPE_SECRET_KEY`, `STRIPE_PRICE_MONTHLY`, `STRIPE_PRICE_YEARLY`, `STRIPE_PRICE_FOUNDER`. The server validates amount, currency and billing interval before checkout.
4. Set canonical `APP_ORIGIN`. Configure the Stripe customer portal in the matching Stripe environment with invoice history, payment methods and cancellation at period end. Subscription price switching is not enabled yet; the portal is cancellation/maintenance only. Existing subscribers should not buy Founder while another subscription is active.
5. Register `/api/billing/webhook` with Stripe and set `STRIPE_WEBHOOK_SECRET`. Events: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `charge.refunded`, `charge.dispute.created`, `charge.dispute.closed`, `payment_intent.succeeded`. Stripe signature verification is mandatory. Do not weaken whole-site preview protection just to receive webhooks: use a deliberately configured reachable webhook endpoint at launch or a scoped approved test-delivery path.
6. Verify hosted Stripe webhook delivery, replay, renewal failure/recovery, cancellation, full Founder refund and the customer portal using isolated test accounts. Test Apple Pay on a supported device/wallet. Card wallets are supported by hosted Checkout; eligibility depends on browser, device and Stripe settings.
7. Set `BILLING_ENABLED=true` only in the intended environment and redeploy after those checks. Sandbox keys must not unlock real paid memberships. Configure Stripe webhook failure alerts and reconcile billing discrepancies before opening broadly.

## Implementation and checks

`backend/payments.py`: server-selected prices, authenticated account/customer mapping, reusable open Checkout sessions, expiration on tier changes, idempotency keys, Stripe-hosted portal, signed and deduplicated events, canonical provider status retrieval under the database lock. Checkout return URLs only refresh membership; they cannot grant access.

`billing_checkouts` stores account-bound checkout sessions; `billing_entitlements` stores subscription/Founder access. Existing `webhook_events` deduplicates deliveries. New tables are created by the normal application migration. No card data enters Tradersecho.

Verified: 28 isolated backend tests; frontend production build; hosted sandbox monthly/yearly paid subscriptions; direct automatic Stripe webhook delivery into PostgreSQL; duplicate subscription guard; customer portal session creation; failed annual renewal with Stripe test clock; successful payment recovery; scheduled cancellation preserving access; immediate cancellation revocation; Founder payment and full refund; signed webhook replay and invalid-signature rejection. Confirmed the test account is absent from the main member database. All test subscriptions are cancelled, unused Checkout sessions expired and the Founder test payment refunded.

Browser limitation: the in-app browser failed to load Stripe's own hosted Checkout CSS. The Tradersecho sandbox banner and plan screen were verified, but end-user card entry and wallet display are not yet browser-verified. Check the final hosted Checkout flow and Apple Pay on a supported device before live sales. No live funds were used.
