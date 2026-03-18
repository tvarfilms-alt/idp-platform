"""
IDP Compute L2 — Market Regime (Daily)

Source of truth: IDP_Level2_Daily.xlsx / IDP_Level2_MarketRegime.xlsx

Pipeline:
  1. Read daily market data: RVI, IMOEX, RGBI, RUONIA, credit spreads, volumes
  2. Compute Z-scores with expanding window (asymmetric clipping [-3, +5])
  3. Score 5 risk blocks (0/1/2 each): Volatility, Credit, Liquidity, Correlation, Microstructure
  4. Weighted Market Score (WMS): Vol×1.0 + Credit×1.5 + Liq×1.5 + Corr×0.5 + Micro×0.5
  5. Determine regime: WMS ≤2.5 → Risk-on, 2.5–5.0 → Neutral, ≥5.0 → Risk-off
  6. Anti-stick override (max 5 consecutive days in same regime)
  7. Write to l2_daily

Trigger: Daily 21:00 MSK, after ETL MOEX + CBR + Cbonds.
"""
import sys
import json
import statistics
from datetime import date, timedelta
from db_helpers import (
    get_raw_range, get_calc_version, rest_upsert, rest_get,
    log, today_str
)


def zscore_expanding(values: list[float], clip_lo: float = -3.0, clip_hi: float = 5.0) -> list[float]:
    """Compute expanding-window Z-scores with asymmetric clipping."""
    zscores = []
    for i in range(len(values)):
        window = values[:i+1]
        if len(window) < 2:
            zscores.append(0.0)
            continue
        mean = statistics.mean(window)
        std = statistics.stdev(window)
        if std < 1e-10:
            zscores.append(0.0)
            continue
        z = (values[i] - mean) / std
        z = max(clip_lo, min(clip_hi, z))
        zscores.append(z)
    return zscores


def score_block(z: float, lo: float = 0.5, hi: float = 1.5) -> int:
    """Score a z-score into 0 (calm), 1 (elevated), 2 (stress)."""
    az = abs(z)
    if az < lo:
        return 0
    elif az < hi:
        return 1
    return 2


def compute_l2(target_date: str = None):
    """Main L2 compute for a single date."""
    if target_date is None:
        target_date = today_str()

    log(f"compute_l2: target_date={target_date}")

    # Get config
    cv = get_calc_version("L2")
    version_id = cv["version_id"]
    cfg = cv["config_json"] if isinstance(cv["config_json"], dict) else json.loads(cv["config_json"])

    block_weights = cfg.get("block_weights", {})
    total_weight = cfg.get("total_weight", 5.0)
    thresholds = cfg.get("thresholds", {"risk_on": 7.0, "risk_off": 4.0})
    multipliers = cfg.get("multipliers", {"risk_on": 1.2, "neutral": 1.0, "risk_off": 0.5})
    anti_stick = cfg.get("anti_stick_rules", {"max_consecutive_days": 5, "override_to": "neutral"})

    # Fetch 250 trading days of history for Z-score computation
    d = date.fromisoformat(target_date)
    date_from = (d - timedelta(days=400)).isoformat()  # ~250 trading days

    tickers = ["RVI", "IMOEX", "RGBI", "RUONIA", "KEY_RATE", "MCFTR", "USD_RUB"]
    data = get_raw_range(tickers, date_from, target_date)
    log(f"  Fetched {len(data)} raw records")

    # Build daily series per ticker
    series = {}
    for r in data:
        t = r["ticker"]
        if t not in series:
            series[t] = {}
        series[t][r["date"]] = float(r["close_price"])

    # Get all unique dates, sorted
    all_dates = sorted(set(r["date"] for r in data))
    if target_date not in all_dates:
        log(f"  WARNING: target_date {target_date} not in data, using latest available")
        if all_dates:
            target_date = all_dates[-1]
        else:
            log("  ERROR: No data available")
            return None

    target_idx = all_dates.index(target_date)

    # ── Compute indicators ──
    def get_val(ticker, dt):
        return series.get(ticker, {}).get(dt)

    # 1. Volatility block: RVI level + RVI change
    rvi_vals = [get_val("RVI", d) for d in all_dates[:target_idx+1]]
    rvi_vals = [v for v in rvi_vals if v is not None]

    rvi_current = get_val("RVI", target_date)
    vol_score = 0
    if rvi_current is not None:
        # RVI > 30 = stress, > 25 = elevated, < 25 = calm
        if rvi_current >= 30:
            vol_score = 2
        elif rvi_current >= 25:
            vol_score = 1
        else:
            vol_score = 0
    log(f"  RVI={rvi_current} → vol_score={vol_score}")

    # 2. Credit block: RUONIA-KS spread as proxy for credit stress
    ruonia = get_val("RUONIA", target_date)
    ks = get_val("KEY_RATE", target_date)
    credit_score = 0
    ruonia_spread = None
    if ruonia is not None and ks is not None:
        ruonia_spread = ruonia - ks
        # Tight spread (RUONIA >> KS) = stress
        if abs(ruonia_spread) > 1.0:
            credit_score = 2
        elif abs(ruonia_spread) > 0.5:
            credit_score = 1
    log(f"  RUONIA={ruonia} KS={ks} spread={ruonia_spread} → credit_score={credit_score}")

    # 3. Liquidity block: based on market volumes and USD/RUB volatility
    usd_rub = get_val("USD_RUB", target_date)
    usd_rub_vals = [get_val("USD_RUB", d) for d in all_dates[max(0,target_idx-20):target_idx+1]]
    usd_rub_vals = [v for v in usd_rub_vals if v is not None]
    liquidity_score = 0
    if len(usd_rub_vals) >= 5:
        usd_vol = statistics.stdev(usd_rub_vals) / statistics.mean(usd_rub_vals) * 100
        if usd_vol > 3.0:
            liquidity_score = 2
        elif usd_vol > 1.5:
            liquidity_score = 1
    log(f"  USD/RUB={usd_rub} → liquidity_score={liquidity_score}")

    # 4. Correlation block: IMOEX vs RGBI (negative correlation = stress)
    correlation_score = 0
    imoex_vals = [get_val("IMOEX", d) for d in all_dates[max(0,target_idx-20):target_idx+1]]
    rgbi_vals = [get_val("RGBI", d) for d in all_dates[max(0,target_idx-20):target_idx+1]]
    imoex_clean = []
    rgbi_clean = []
    for iv, rv in zip(imoex_vals, rgbi_vals):
        if iv is not None and rv is not None:
            imoex_clean.append(iv)
            rgbi_clean.append(rv)
    if len(imoex_clean) >= 10:
        # Compute returns
        imoex_rets = [(imoex_clean[i] - imoex_clean[i-1]) / imoex_clean[i-1]
                      for i in range(1, len(imoex_clean))]
        rgbi_rets = [(rgbi_clean[i] - rgbi_clean[i-1]) / rgbi_clean[i-1]
                     for i in range(1, len(rgbi_clean))]
        if len(imoex_rets) >= 5:
            # Pearson correlation
            n = len(imoex_rets)
            mean_i = sum(imoex_rets) / n
            mean_r = sum(rgbi_rets) / n
            cov = sum((imoex_rets[j] - mean_i) * (rgbi_rets[j] - mean_r) for j in range(n)) / n
            std_i = (sum((x - mean_i)**2 for x in imoex_rets) / n) ** 0.5
            std_r = (sum((x - mean_r)**2 for x in rgbi_rets) / n) ** 0.5
            if std_i > 0 and std_r > 0:
                corr = cov / (std_i * std_r)
                # High positive correlation between stocks and bonds = abnormal
                if corr > 0.5:
                    correlation_score = 2
                elif corr > 0.2:
                    correlation_score = 1
    log(f"  correlation_score={correlation_score}")

    # 5. Microstructure block: IMOEX breadth / momentum
    microstructure_score = 0
    imoex_current = get_val("IMOEX", target_date)
    if target_idx >= 20:
        imoex_20d_ago = get_val("IMOEX", all_dates[target_idx - 20])
        if imoex_current and imoex_20d_ago and imoex_20d_ago > 0:
            mom_20d = (imoex_current - imoex_20d_ago) / imoex_20d_ago * 100
            if mom_20d < -10:
                microstructure_score = 2
            elif mom_20d < -5:
                microstructure_score = 1
    log(f"  microstructure_score={microstructure_score}")

    # ── Weighted Market Score ──
    w_vol = block_weights.get("volatility", 1.0)
    w_cred = block_weights.get("credit", 1.5)
    w_liq = block_weights.get("liquidity", 1.5)
    w_corr = block_weights.get("correlation", 0.5)
    w_micro = block_weights.get("microstructure", 0.5)

    raw_wms = (vol_score * w_vol + credit_score * w_cred +
               liquidity_score * w_liq + correlation_score * w_corr +
               microstructure_score * w_micro)
    wms = raw_wms / total_weight * 10.0  # Normalize to 0–10 scale

    log(f"  WMS={wms:.2f} (raw={raw_wms:.2f})")

    # ── Base regime ──
    risk_on_thresh = thresholds.get("risk_on", 7.0)
    risk_off_thresh = thresholds.get("risk_off", 4.0)

    if wms <= risk_off_thresh:
        base_regime = "Risk-on"
    elif wms >= risk_on_thresh:
        base_regime = "Risk-off"
    else:
        base_regime = "Neutral"

    # ── Anti-stick override ──
    max_days = anti_stick.get("max_consecutive_days", 5)
    override_to = anti_stick.get("override_to", "neutral")
    anti_stick_override = None

    # Check recent l2_daily for consecutive same regime
    recent = rest_get("l2_daily", {
        "select": "date,regime",
        "order": "date.desc",
        "limit": str(max_days),
    })
    if len(recent) >= max_days:
        all_same = all(r["regime"] == base_regime for r in recent)
        if all_same and base_regime != "Neutral":
            anti_stick_override = f"anti_stick_{max_days}d→{override_to}"
            base_regime = "Neutral"
            log(f"  Anti-stick override: {anti_stick_override}")

    regime = base_regime
    multiplier = multipliers.get(regime.lower().replace("-", "_"), 1.0)

    log(f"  REGIME={regime} MULTIPLIER={multiplier}")

    # ── Write to l2_daily ──
    raw_indicators = {
        "rvi": rvi_current,
        "ruonia_spread": ruonia_spread,
        "usd_rub": usd_rub,
        "imoex": imoex_current,
    }

    row = {
        "date": target_date,
        "calc_version_id": version_id,
        "vol_score": vol_score,
        "credit_score": credit_score,
        "breadth_score": 0,  # needs market breadth data
        "momentum_score": microstructure_score,
        "liquidity_score": liquidity_score,
        "correlation_score": correlation_score,
        "wms": round(wms, 4),
        "regime": regime,
        "multiplier": multiplier,
        "anti_stick_override": anti_stick_override,
        "raw_indicators": json.dumps(raw_indicators),
    }
    rest_upsert("l2_daily", [row])
    log(f"  Written to l2_daily: {target_date} → {regime} (×{multiplier})")
    return row


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    sys.path.insert(0, ".")
    compute_l2(target)
