"""
IDP Compute L3 -- Cross-Section Stock Screening (Weekly)

Source of truth: IDP_Level3_CrossSection.xlsx + IDP_Level3_Documentation.md

Pipeline:
  1. Read stock prices (50 IMOEX tickers) and FM fundamentals from raw_market_data
  2. Compute returns: 1M, 3M, 6M
  3. Momentum factor: percentile rank of combined alpha (25% x 50d + 50% x 20d + 25% x 7d)
  4. Relative Value factor: composite of P/E, P/BV, EV/EBITDA percentiles (low = good)
  5. Quality factor: winsorized ROE rank with debt penalty
  6. IdeaScore = Momentum x weight + RV x weight + Quality x weight
  7. Signal: BUY (top 20%), AVOID (bottom 20%), HOLD (middle)
  8. Write to l3_screening

Trigger: Monday 08:00 MSK, after FM data loaded.
"""
import json
import statistics
from datetime import date, datetime, timedelta
from db_helpers import (
    get_raw_range, get_calc_version, rest_upsert,
    get_instruments, log, today_str
)


def _percentile_rank(values: list, reverse: bool = False) -> list:
    """
    Assign percentile ranks (0..1) to values.
    If reverse=True, lower raw values get higher percentile (used for valuation).
    None values get 0.5 (neutral).
    """
    indexed = [(i, v) for i, v in enumerate(values)]
    valid = [(i, v) for i, v in indexed if v is not None]
    n = len(valid)
    if n == 0:
        return [0.5] * len(values)

    # Sort ascending
    valid_sorted = sorted(valid, key=lambda x: x[1])

    ranks = {}
    for rank_pos, (idx, val) in enumerate(valid_sorted):
        pctile = rank_pos / max(n - 1, 1)
        if reverse:
            pctile = 1.0 - pctile
        ranks[idx] = pctile

    result = []
    for i in range(len(values)):
        result.append(ranks.get(i, 0.5))
    return result


def _winsorize(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clip value to [lo, hi]."""
    if val is None:
        return None
    return max(lo, min(hi, val))


def _safe_float(val, default=None):
    """Safely convert to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def compute_l3(target_date: str = None):
    """Main L3 cross-section screening."""
    if target_date:
        td = date.fromisoformat(target_date)
    else:
        td = date.today()

    log(f"L3 Compute: target date = {td.isoformat()}")

    # Get calc version
    try:
        cv = get_calc_version("L3")
        version_id = cv["version_id"]
        config = cv.get("config_json", {})
        if isinstance(config, str):
            config = json.loads(config)
    except Exception as e:
        log(f"Warning: no calc_version for L3, using defaults: {e}")
        version_id = 1
        config = {}

    # Factor weights from config or defaults
    w_mom = config.get("w_momentum", 0.35)
    w_rv = config.get("w_rv", 0.35)
    w_qual = config.get("w_quality", 0.30)

    # Get active L3 instruments (stocks)
    instruments = get_instruments(level="L3", active_only=True)
    if not instruments:
        # Fallback: get all active instruments
        instruments = get_instruments(active_only=True)
    tickers = [inst["ticker"] for inst in instruments]

    if not tickers:
        log("L3: No instruments found, skipping")
        return []

    log(f"L3: Processing {len(tickers)} tickers")

    # Fetch 7 months of price data for return calculations
    date_from = (td - timedelta(days=210)).isoformat()
    date_to = td.isoformat()

    raw = get_raw_range(tickers, date_from, date_to)

    # Group by ticker
    by_ticker = {}
    for row in raw:
        t = row["ticker"]
        by_ticker.setdefault(t, []).append(row)

    # ---- Build per-stock metrics ----
    stocks = []
    for ticker in tickers:
        prices = by_ticker.get(ticker, [])
        if not prices:
            continue

        # Current price
        current = prices[-1]
        price = _safe_float(current["close_price"])
        if price is None or price <= 0:
            continue

        # Extract fundamentals from extra_json
        extra = current.get("extra_json")
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except (json.JSONDecodeError, TypeError):
                extra = {}
        if not isinstance(extra, dict):
            extra = {}

        pe = _safe_float(extra.get("pe"))
        pbv = _safe_float(extra.get("pbv"))
        ev_ebitda = _safe_float(extra.get("ev_ebitda"))
        roe = _safe_float(extra.get("roe"))
        debt_ratio = _safe_float(extra.get("debt_ratio"))
        dy = _safe_float(extra.get("dy"))

        # Calculate returns
        price_list = [_safe_float(p["close_price"]) for p in prices if _safe_float(p["close_price"]) is not None]
        n_prices = len(price_list)

        # Approximate trading days: 1M~21, 3M~63, 6M~126
        return_1m = (price / price_list[-min(21, n_prices)] - 1.0) if n_prices >= 5 else None
        return_3m = (price / price_list[-min(63, n_prices)] - 1.0) if n_prices >= 20 else None
        return_6m = (price / price_list[-min(126, n_prices)] - 1.0) if n_prices >= 40 else None

        # Momentum alpha: 25% x ~50d + 50% x ~20d + 25% x ~7d
        ret_50d = (price / price_list[-min(50, n_prices)] - 1.0) if n_prices >= 10 else 0.0
        ret_20d = (price / price_list[-min(20, n_prices)] - 1.0) if n_prices >= 5 else 0.0
        ret_7d = (price / price_list[-min(7, n_prices)] - 1.0) if n_prices >= 3 else 0.0
        mom_alpha = 0.25 * ret_50d + 0.50 * ret_20d + 0.25 * ret_7d

        # Relative Value composite (lower is better for PE, PBV, EV/EBITDA)
        rv_raw = None
        rv_components = [pe, pbv, ev_ebitda]
        valid_rv = [v for v in rv_components if v is not None and v > 0]
        if valid_rv:
            # Normalize: we'll rank these later across stocks
            rv_raw = sum(valid_rv) / len(valid_rv)  # placeholder, ranking happens below

        # Quality: ROE with debt penalty
        qual_raw = None
        if roe is not None:
            roe_w = _winsorize(roe, -50, 100)
            penalty = 0.0
            if debt_ratio is not None and debt_ratio > 1.0:
                penalty = (debt_ratio - 1.0) * 10.0  # penalize high leverage
            qual_raw = roe_w - penalty

        stocks.append({
            "ticker": ticker,
            "price": price,
            "pe": pe,
            "pbv": pbv,
            "ev_ebitda": ev_ebitda,
            "roe": roe,
            "debt_ratio": debt_ratio,
            "dy": dy,
            "return_1m": round(return_1m, 6) if return_1m is not None else None,
            "return_3m": round(return_3m, 6) if return_3m is not None else None,
            "return_6m": round(return_6m, 6) if return_6m is not None else None,
            "mom_alpha": mom_alpha,
            "rv_raw": rv_raw,
            "qual_raw": qual_raw,
        })

    if not stocks:
        log("L3: No stocks with valid data, skipping")
        return []

    log(f"L3: {len(stocks)} stocks with valid data")

    # ---- Cross-sectional ranking ----
    mom_values = [s["mom_alpha"] for s in stocks]
    rv_values = [s["rv_raw"] for s in stocks]
    qual_values = [s["qual_raw"] for s in stocks]

    mom_pctiles = _percentile_rank(mom_values, reverse=False)  # higher momentum = higher rank
    rv_pctiles = _percentile_rank(rv_values, reverse=True)     # lower valuation = higher rank
    qual_pctiles = _percentile_rank(qual_values, reverse=False)  # higher quality = higher rank

    # ---- Compute IdeaScore and Signal ----
    rows = []
    for i, s in enumerate(stocks):
        mp = mom_pctiles[i]
        rp = rv_pctiles[i]
        qp = qual_pctiles[i]

        idea_score = w_mom * mp + w_rv * rp + w_qual * qp
        idea_score = round(idea_score, 4)

        s["mom_pctile"] = round(mp, 4)
        s["rv_pctile"] = round(rp, 4)
        s["qual_pctile"] = round(qp, 4)
        s["idea_score"] = idea_score

    # Assign signals based on IdeaScore ranking
    stocks_sorted = sorted(enumerate(stocks), key=lambda x: x[1]["idea_score"], reverse=True)
    n_stocks = len(stocks_sorted)
    top_20 = max(1, int(n_stocks * 0.2))
    bottom_20 = max(1, int(n_stocks * 0.2))

    signals = ["HOLD"] * n_stocks
    for rank, (orig_idx, _) in enumerate(stocks_sorted):
        if rank < top_20:
            signals[orig_idx] = "BUY"
        elif rank >= n_stocks - bottom_20:
            signals[orig_idx] = "AVOID"

    # Build output rows
    now = datetime.utcnow().isoformat() + "Z"
    for i, s in enumerate(stocks):
        row = {
            "date": td.isoformat(),
            "ticker": s["ticker"],
            "calc_version_id": version_id,
            "pe": s["pe"],
            "pbv": s["pbv"],
            "ev_ebitda": s["ev_ebitda"],
            "roe": s["roe"],
            "debt_ratio": s["debt_ratio"],
            "dy": s["dy"],
            "price": s["price"],
            "return_1m": s["return_1m"],
            "return_3m": s["return_3m"],
            "return_6m": s["return_6m"],
            "mom_pctile": s["mom_pctile"],
            "rv_pctile": s["rv_pctile"],
            "qual_pctile": s["qual_pctile"],
            "idea_score": s["idea_score"],
            "signal": signals[i],
            "computed_at": now,
        }
        rows.append(row)

    # Upsert to l3_screening
    n = rest_upsert("l3_screening", rows)
    log(f"L3: upserted {n} row(s) to l3_screening")

    buy_count = sum(1 for r in rows if r["signal"] == "BUY")
    avoid_count = sum(1 for r in rows if r["signal"] == "AVOID")
    log(f"L3: BUY={buy_count}, HOLD={n - buy_count - avoid_count}, AVOID={avoid_count}")

    return rows
