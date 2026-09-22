# TradingView links

Shared ranking tables and universal ticker details link to TradingView for all plans. No third-party script or embed loads.

tradingview-symbols.json covers 357 stocks, based on the SEC exchange directory and Nasdaq Trader otherlisted.txt retrieved September 19, 2026. Nasdaq directory corrects SEC groupings for NYSE American (TradingView AMEX): DNN, UEC, URG, UUUU. Refresh mappings when listings change. Unknown future tickers get an explicitly labelled search link rather than a guessed exchange.

Affiliate tracking remains OFF until the owner supplies a verified partner link. Set public numeric VITE_TRADINGVIEW_AFFILIATE_ID at build time and redeploy after confirming aff_id against the issued link. Disclosure and sponsored link attributes activate together. Never put credentials in this setting.

Signup: https://www.tradingview.com/partner-program/ . Current signup page offers immediate partner link access, no minimum audience, account/traffic checks before first payout, monthly PayPal payments, fixed commissions of $10-$400. Older rules text still mentions 30% recurring; confirm accepted dashboard terms before forecasting revenue.

Validation: frontend build; full universe map coverage; live intraday and 24-hour rankings; ticker detail button; TradingView NASDAQ and NYSE destination spot checks.

## Activated September 19, 2026
Owner supplied https://www.tradingview.com/?aff_id=1171135. Public VITE_TRADINGVIEW_AFFILIATE_ID=1171135 saved in Production and Preview. Per-stock links retain exchange mapping and append this ID; disclosure and sponsored attributes activate. Attribution format is documented in TradingView partner FAQ; actual conversions/payout eligibility must be checked in the owner dashboard.
