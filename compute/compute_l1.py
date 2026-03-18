"""
IDP Compute L1 — Macro Regime (Monthly)

Source of truth: IDP_Level1_MacroRegime_v5.xlsx

Pipeline:
  1. Read monthly macro data from raw_market_data (PMI, CPI, KS, IMOEX, RGBI, BCOM, Urals)
  2. Compute Growth axis: growth_base → commodity_score → growth_v5
  3. Compute Monetary axis: monet_base → ks_momentum → monet_v5
  4. Determine regime from 3×3 matrix + stress override
  5. Map regime → risk_cap
  6. Write to l1_regime table

Trigger: 1st of each month, after all L1 indicators are loaded.
"""
