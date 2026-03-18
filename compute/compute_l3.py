"""
IDP Compute L3 — Cross-Section Stock Screening (Weekly)

Source of truth: IDP_Level3_CrossSection.xlsx + IDP_Level3_Documentation.md

Pipeline:
  1. Read stock prices (50 IMOEX tickers) and FM fundamentals from raw_market_data
  2. Compute returns: 1M, 3M, 6M
  3. Momentum factor: percentile rank of combined alpha (25% × 50d + 50% × 20d + 25% × 7d)
  4. Relative Value factor: composite of P/E, P/BV, EV/EBITDA percentiles (low = good)
  5. Quality factor: winsorized ROE rank with debt penalty
  6. IdeaScore = Momentum × weight + RV × weight + Quality × weight
  7. Signal: BUY (top 20%), AVOID (bottom 20%), HOLD (middle)
  8. Write to l3_screening

Trigger: Monday 08:00 MSK, after FM data loaded.
"""