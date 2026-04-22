from datetime import datetime, timedelta


def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 1)


def calc_macd(prices, fast=12, slow=26, signal=9):
    """Returns dict: macd_line, signal_line, histogram, crossover ('bullish'/'bearish'/None)."""
    if len(prices) < slow + signal:
        return None

    def ema(data, span):
        k = 2 / (span + 1)
        result = [data[0]]
        for p in data[1:]:
            result.append(p * k + result[-1] * (1 - k))
        return result

    ema_fast   = ema(prices, fast)
    ema_slow   = ema(prices, slow)
    macd_line  = [f - s for f, s in zip(ema_fast, ema_slow)]
    sig_line   = ema(macd_line[slow - 1:], signal)
    # align: signal starts at index (slow-1+signal-1) of original
    offset     = slow - 1
    hist_vals  = [macd_line[offset + i] - sig_line[i] for i in range(len(sig_line))]

    macd_now   = round(macd_line[-1], 4)
    sig_now    = round(sig_line[-1], 4)
    hist_now   = round(hist_vals[-1], 4)

    crossover = None
    if len(hist_vals) >= 2:
        if hist_vals[-2] < 0 and hist_vals[-1] >= 0:
            crossover = "bullish"
        elif hist_vals[-2] > 0 and hist_vals[-1] <= 0:
            crossover = "bearish"

    return {
        "macd":       macd_now,
        "signal":     sig_now,
        "histogram":  hist_now,
        "crossover":  crossover,
        "trending_up": macd_now > sig_now,
    }


def calc_bollinger_bands(prices, period=20, num_std=2):
    """Returns dict: upper, middle, lower, percent_b, bandwidth, squeeze."""
    if len(prices) < period:
        return None
    window  = prices[-period:]
    middle  = sum(window) / period
    variance = sum((p - middle) ** 2 for p in window) / period
    std     = variance ** 0.5
    upper   = round(middle + num_std * std, 2)
    lower   = round(middle - num_std * std, 2)
    middle  = round(middle, 2)
    price   = prices[-1]
    pct_b   = round((price - lower) / (upper - lower), 3) if upper != lower else 0.5
    bw      = round((upper - lower) / middle * 100, 2) if middle else 0
    # squeeze: bandwidth < 10% is historically tight (coiled spring)
    squeeze = bw < 10
    return {
        "upper":     upper,
        "middle":    middle,
        "lower":     lower,
        "percent_b": pct_b,   # 0=at lower, 1=at upper, >1 breakout above
        "bandwidth": bw,
        "squeeze":   squeeze,
    }


def find_support_resistance(hist, lookback=60, pivot_strength=3):
    """
    Identify S/R levels from recent swing highs and lows.
    Returns dict: nearest_support, nearest_resistance, levels (list).
    """
    if len(hist) < lookback + pivot_strength * 2:
        return {"nearest_support": None, "nearest_resistance": None, "levels": []}

    highs  = list(hist["High"].iloc[-lookback:])
    lows   = list(hist["Low"].iloc[-lookback:])
    price  = float(hist["Close"].iloc[-1])
    n      = len(highs)
    levels = []

    for i in range(pivot_strength, n - pivot_strength):
        # swing high
        if highs[i] == max(highs[i - pivot_strength: i + pivot_strength + 1]):
            levels.append(round(highs[i], 2))
        # swing low
        if lows[i] == min(lows[i - pivot_strength: i + pivot_strength + 1]):
            levels.append(round(lows[i], 2))

    # deduplicate levels within 0.5% of each other
    levels = sorted(set(levels))
    deduped = []
    for lv in levels:
        if not deduped or abs(lv - deduped[-1]) / deduped[-1] > 0.005:
            deduped.append(lv)

    supports    = [lv for lv in deduped if lv < price]
    resistances = [lv for lv in deduped if lv > price]

    return {
        "nearest_support":    max(supports)    if supports    else None,
        "nearest_resistance": min(resistances) if resistances else None,
        "levels":             deduped,
    }


def calc_rvol(hist):
    if len(hist) < 21:
        return None
    avg = hist["Volume"].iloc[-21:-1].mean()
    today = hist["Volume"].iloc[-1]
    return round(today / avg, 2) if avg > 0 else None


def calc_atr(hist, period=14):
    if len(hist) < period + 1:
        return None
    trs = []
    for i in range(1, len(hist)):
        h  = float(hist["High"].iloc[i])
        l  = float(hist["Low"].iloc[i])
        pc = float(hist["Close"].iloc[i - 1])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return round(sum(trs[-period:]) / period, 2)


def get_trend(price, hist):
    closes = list(hist["Close"])
    ma50  = round(sum(closes[-50:])  / min(50,  len(closes)), 2) if len(closes) >= 10 else None
    ma200 = round(sum(closes[-200:]) / min(200, len(closes)), 2) if len(closes) >= 50 else None
    return (
        ma50, ma200,
        price > ma50  if ma50  else None,
        price > ma200 if ma200 else None,
    )


def get_vol_structure(hist):
    if len(hist) < 10:
        return None, None, None
    r      = hist.tail(10)
    up     = r[r["Close"] > r["Open"]]
    dn     = r[r["Close"] <= r["Open"]]
    avg_up = up["Volume"].mean() if len(up) else 0
    avg_dn = dn["Volume"].mean() if len(dn) else 1
    return round(avg_up), round(avg_dn), round(avg_up / avg_dn, 2) if avg_dn else None


def detect_catalysts(news_items):
    keywords = {
        "earnings": ["earnings", "eps", "revenue", "beat", "miss", "quarterly", "guidance"],
        "fda":      ["fda", "approval", "clinical", "trial", "drug", "nda", "bla", "pdufa"],
        "merger":   ["merger", "acquisition", "buyout", "takeover", "deal", "acquired"],
        "analyst":  ["upgrade", "downgrade", "price target", "analyst", "rating", "initiated"],
        "insider":  ["insider", "ceo", "cfo", "director", "officer", "bought", "purchased"],
        "contract": ["contract", "partnership", "agreement", "awarded", "won", "signed"],
    }
    found = set()
    for item in news_items:
        title = (item.get("title") or "").lower()
        for cat, kws in keywords.items():
            if any(k in title for k in kws):
                found.add(cat)
    return list(found)


def score_stock(d):
    bd = {}
    red_flags = []

    # --- Trend (max 18) — most important for 1-week holds ---
    t        = 0
    above50  = d.get("above_50ma")
    above200 = d.get("above_200ma")
    if above50  is True:    t += 9
    elif above50 is False:  t -= 5
    if above200 is True:    t += 9
    elif above200 is False: t -= 5

    prox = d.get("week52_proximity_pct")
    if prox is not None:
        if prox <= 5:    t += 2
        elif prox <= 15: t += 1
        elif prox >= 50:
            t -= 4
            red_flags.append("More than 50% below 52W high")

    bd["trend"] = max(min(t, 18), -10)

    # --- RVOL (max 18) ---
    rv = d.get("rvol") or 0
    if rv >= 3:     bd["rvol"] = 18
    elif rv >= 2:   bd["rvol"] = 13
    elif rv >= 1.5: bd["rvol"] = 9
    elif rv >= 1:   bd["rvol"] = 4
    elif rv >= 0.5: bd["rvol"] = 1
    else:           bd["rvol"] = 0

    # --- Catalyst (max 15) ---
    c    = 0
    cats = d.get("catalysts", [])
    if "earnings" in cats: c += 8
    if "fda"      in cats: c += 10
    if "merger"   in cats: c += 10
    if "analyst"  in cats: c += 5
    if "contract" in cats: c += 6
    if "insider"  in cats: c += 4
    ins = len(d.get("insider_trades", []))
    if ins >= 2:   c += 5
    elif ins >= 1: c += 2
    bd["catalyst"] = min(c, 15)

    # --- Support/Resistance proximity (max 14) ---
    sr_score = 0
    sr    = d.get("support_resistance") or {}
    price = d.get("price", 0)
    if sr and price:
        support = sr.get("nearest_support")
        resist  = sr.get("nearest_resistance")
        if support:
            dist_pct = (price - support) / price * 100
            if dist_pct <= 1.5:
                sr_score += 14
            elif dist_pct <= 3.0:
                sr_score += 9
            elif dist_pct <= 5.0:
                sr_score += 4
        if resist:
            dist_pct = (resist - price) / price * 100
            if dist_pct <= 1.5:
                sr_score -= 7
                red_flags.append("Price approaching key resistance")
            elif dist_pct <= 3.0:
                sr_score -= 3

    bd["support_resistance"] = max(min(sr_score, 14), -7)

    # --- MACD (max 13) ---
    macd_score = 0
    macd = d.get("macd") or {}
    if macd:
        if macd.get("crossover") == "bullish":
            macd_score += 11
        elif macd.get("crossover") == "bearish":
            macd_score -= 8
            red_flags.append("MACD bearish crossover")
        elif macd.get("trending_up"):
            macd_score += 6

        hist_val = macd.get("histogram", 0)
        if hist_val > 0 and macd.get("trending_up"):
            macd_score += 2
    bd["macd"] = max(min(macd_score, 13), -8)

    # --- Momentum (max 11) — RSI only; day % de-emphasized ---
    m   = 0
    rsi = d.get("rsi") or 0
    if 55 <= rsi <= 72:   m += 8
    elif 40 <= rsi < 55:  m += 5
    elif rsi > 72:        m += 3
    elif rsi < 30:        m += 1
    else:                 m += 2

    chg = d.get("change_pct", 0)
    if chg >= 5:    m += 3
    elif chg >= 2:  m += 2
    elif chg >= 0:  m += 1

    vol_ratio = d.get("vol_ratio") or 1
    if chg < 0 and vol_ratio < 1:
        m -= 3
        red_flags.append("Selling on above-avg volume")

    bd["momentum"] = max(min(m, 11), 0)

    # --- Bollinger Bands (max 6) ---
    bb_score = 0
    bb = d.get("bollinger") or {}
    if bb:
        pct_b  = bb.get("percent_b", 0.5)
        squeeze = bb.get("squeeze", False)
        if pct_b <= 0.15:
            bb_score += 5
        elif pct_b <= 0.30:
            bb_score += 3
        elif pct_b >= 1.0:
            rvol = d.get("rvol") or 1
            if rvol >= 1.5:
                bb_score += 4
            else:
                bb_score += 1
                red_flags.append("BB breakout on weak volume")
        elif pct_b >= 0.85:
            bb_score += 2
        if squeeze:
            bb_score += 1

    bd["bollinger"] = max(min(bb_score, 6), 0)

    # --- Float (max 3) ---
    fl = (d.get("float_shares") or 0) / 1e6
    if 0 < fl < 20:  bd["float"] = 3
    elif fl < 50:    bd["float"] = 2
    elif fl < 100:   bd["float"] = 1
    else:            bd["float"] = 0

    # --- Short squeeze (max 2) ---
    sp = d.get("short_pct_float") or 0
    dc = d.get("days_to_cover") or 0
    sq = 0
    if sp >= 30:   sq += 2
    elif sp >= 20: sq += 1
    if dc >= 5:    sq += 1
    bd["squeeze"] = min(sq, 2)

    # --- Hard penalties ---
    gap       = d.get("gap_pct", 0)
    penalties = 0
    if rsi > 80:
        penalties += 5
        red_flags.append("RSI overbought (>80) — chasing a top")
    if rsi < 25:
        penalties += 3
        red_flags.append("RSI extremely oversold — falling knife risk")
    if rv < 0.7:
        penalties += 5
        red_flags.append("Very low volume — no institutional interest")
    if above50 is False and above200 is False:
        penalties += 5
        red_flags.append("Below both MAs — confirmed downtrend")
    if chg <= -5:
        penalties += 5
        red_flags.append(f"Large down day ({chg:.1f}%) — momentum broken")
    if gap < -3:
        penalties += 3
        red_flags.append(f"Gap down ({gap:.1f}%) — sellers in control")

    total = max(sum(bd.values()) - penalties, 0)

    if total >= 72:   rating, color = "STRONG BUY",      "#4ade80"
    elif total >= 55: rating, color = "BUY",              "#86efac"
    elif total >= 38: rating, color = "NEUTRAL",          "#fbbf24"
    elif total >= 22: rating, color = "WEAK — HIGH RISK", "#fb923c"
    else:             rating, color = "AVOID",            "#f87171"

    return {
        "total":     total,
        "breakdown": bd,
        "penalties": penalties,
        "red_flags": red_flags,
        "rating":    rating,
        "color":     color,
    }


def _add_trading_days(start, n):
    d     = start
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def estimate_trade_plan(d, score, market=None):
    price     = d.get("price", 0)
    atr       = d.get("atr") or (price * 0.025)
    total     = score.get("total", 0)
    rvol      = d.get("rvol") or 1
    short_pct = d.get("short_pct_float") or 0
    above50   = d.get("above_50ma")
    above200  = d.get("above_200ma")
    rsi       = d.get("rsi") or 50
    chg       = d.get("change_pct", 0)
    mkt_mult  = (market or {}).get("return_multiplier", 1.0)

    sr       = d.get("support_resistance") or {}
    support  = sr.get("nearest_support")
    resist   = sr.get("nearest_resistance")
    bb       = d.get("bollinger") or {}
    bb_lower = bb.get("lower")
    bb_upper = bb.get("upper")
    macd     = d.get("macd") or {}

    if total >= 72:   conviction, hold_days = "High",     5
    elif total >= 55: conviction, hold_days = "Moderate", 4
    elif total >= 38: conviction, hold_days = "Low",      3
    else:             conviction, hold_days = "Very Low", 2

    if rvol < 1 or (above50 is False and above200 is False):
        hold_days = max(hold_days - 1, 2)

    entry_date = datetime.now()
    exit_date  = _add_trading_days(entry_date, hold_days)

    # --- Stop loss: use nearest support or BB lower if tighter than ATR stop ---
    atr_stop = round(price - atr * 1.2, 2)
    if support and support > atr_stop and support < price * 0.98:
        # place stop just below the support level
        stop_loss = round(support * 0.992, 2)
    elif bb_lower and bb_lower > atr_stop and bb_lower < price * 0.99:
        stop_loss = round(bb_lower * 0.995, 2)
    else:
        stop_loss = atr_stop
    stop_pct = round((stop_loss - price) / price * 100, 1)

    # --- Bull target: use nearest resistance or BB upper if closer than raw % ---
    bull_pct = round(min((total / 100) * 18 + (rvol - 1) * 2, 25), 1)
    if short_pct >= 20:
        bull_pct = round(min(bull_pct * 1.3, 35), 1)
    bull_pct = round(bull_pct * mkt_mult, 1)

    # MACD boost: fresh crossover adds conviction
    if macd.get("crossover") == "bullish":
        bull_pct = round(min(bull_pct * 1.10, 40), 1)

    # Resistance cap: if resistance (or BB upper) is closer than our bull target, cap there
    cap_price = None
    if resist:
        cap_price = resist
    elif bb_upper and bb_upper > price:
        cap_price = bb_upper
    if cap_price:
        cap_pct = round((cap_price - price) / price * 100, 1)
        if cap_pct < bull_pct:
            bull_pct = cap_pct

    base_mult = 0.45 if (above50 is False or above200 is False) else 0.55
    base_pct  = round(bull_pct * base_mult, 1)

    bear_mkt  = 1.0 + max(0, 1.0 - mkt_mult)
    atr_pct   = (atr / price) if price else 0.025
    if total < 38 or (above50 is False and above200 is False):
        bear_pct = round(-(atr_pct * 100 * 2.5 * bear_mkt), 1)
    elif rsi > 72 or chg >= 8:
        bear_pct = round(-(atr_pct * 100 * 2.0 * bear_mkt), 1)
    else:
        bear_pct = round(stop_pct * 1.1 * bear_mkt, 1)

    if total >= 72:   p_bull, p_base, p_bear = 40, 40, 20
    elif total >= 55: p_bull, p_base, p_bear = 30, 40, 30
    elif total >= 38: p_bull, p_base, p_bear = 20, 35, 45
    else:             p_bull, p_base, p_bear = 10, 25, 65

    ev      = round((p_bull / 100) * bull_pct + (p_base / 100) * base_pct + (p_bear / 100) * bear_pct, 1)
    avg_win = (bull_pct + base_pct) / 2
    avg_loss = abs(bear_pct)
    rr_ratio = round(avg_win / avg_loss, 2) if avg_loss else 0

    scenarios = [
        {
            "label": "Bull Case", "color": "#4ade80",
            "probability": p_bull, "gain_pct": bull_pct,
            "price_target": round(price * (1 + bull_pct / 100), 2),
            "description": "Momentum holds, volume stays elevated, no major resistance",
            "exit_date": _add_trading_days(entry_date, hold_days).strftime("%b %d"),
        },
        {
            "label": "Base Case", "color": "#fbbf24",
            "probability": p_base, "gain_pct": base_pct,
            "price_target": round(price * (1 + base_pct / 100), 2),
            "description": "Partial move then stall, exit at resistance",
            "exit_date": _add_trading_days(entry_date, max(hold_days - 1, 1)).strftime("%b %d"),
        },
        {
            "label": "Bear Case", "color": "#f87171",
            "probability": p_bear, "gain_pct": bear_pct,
            "price_target": round(price * (1 + bear_pct / 100), 2),
            "description": "Setup fails, stop triggered or trend reverses",
            "exit_date": _add_trading_days(entry_date, 2).strftime("%b %d"),
        },
    ]

    return {
        "entry_date":        entry_date.strftime("%b %d, %Y"),
        "recommended_exit":  exit_date.strftime("%b %d, %Y"),
        "hold_days":         hold_days,
        "stop_loss":         stop_loss,
        "stop_pct":          stop_pct,
        "conviction":        conviction,
        "rr_ratio":          rr_ratio,
        "expected_value":    ev,
        "scenarios":         scenarios,
        "base_bull_pct":     bull_pct,
        "base_base_pct":     base_pct,
        "base_bear_pct":     bear_pct,
        "market_multiplier": mkt_mult,
        "nearest_support":   support,
        "nearest_resistance": resist,
    }
