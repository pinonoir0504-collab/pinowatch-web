"""Best-effort Japanese equities daily snapshot. Unofficial Yahoo data can fail.
Not a licensed exchange feed; no guarantee of full coverage or availability.
"""
import json, time, datetime as dt
from pathlib import Path
import pandas as pd
import yfinance as yf

JPX = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xlsx"
OUT = Path("data/latest.json")
OUT.parent.mkdir(exist_ok=True)
jst = dt.timezone(dt.timedelta(hours=9))
now = dt.datetime.now(jst)
def fetch_universe():
    df = pd.read_excel(JPX, engine='openpyxl', dtype={'コード': str})
    df.columns = [str(x).strip() for x in df.columns]
    code_col = next(c for c in df if "コード" in c)
    name_col = next(c for c in df if "銘柄名" in c)
    market_col = next(c for c in df if "市場・商品区分" in c)
    records = []
    for _, row in df.iterrows():
        code = str(row[code_col]).strip()
        market = str(row[market_col])
        if len(code) != 4 or not code[0].isdigit(): continue
        if not any(m in market for m in ("プライム", "スタンダード", "グロース")): continue
        records.append((code, str(row[name_col]), market))
    return records

universe = fetch_universe()
rows = []
errors = []
# Batch downloads avoid one HTTP request per symbol.
print(f"Universe: {len(universe)} symbols", flush=True)
for offset in range(0, len(universe), 60):
    print(f"Fetching {offset+1}-{min(offset+60,len(universe))}/{len(universe)}", flush=True)
    part = universe[offset:offset+60]
    tickers = [code + ".T" for code, _, _ in part]
    try:
        hist = yf.download(tickers, period="ytd", interval="1d", auto_adjust=False,
                           group_by="ticker", threads=False, progress=False, timeout=12)
        for code, name, market in part:
            try:
                h = hist[tickers[part.index((code,name,market))]] if isinstance(hist.columns, pd.MultiIndex) else hist
                h = h.dropna(subset=["Close", "High", "Low"])
                if h.empty: continue
                latest = h.iloc[-1]
                day = str(h.index[-1].date())
                year_hi = float(h["High"].max())
                year_lo = float(h["Low"].min())
                hi = float(latest["High"]); lo = float(latest["Low"])
                if hi >= year_hi - 1e-6 or lo <= year_lo + 1e-6:
                    rows.append({"code":code,"name":name,"market":market,"date":day,
                        "close":round(float(latest["Close"]),2),
                        "yearHigh":round(year_hi,2),"yearLow":round(year_lo,2),
                        "highUpdated":hi >= year_hi-1e-6,"lowUpdated":lo <= year_lo+1e-6,
                        "dividendYield":None})
            except Exception as e: errors.append(code + ": " + str(e)[:100])
    except Exception as e: errors.append("batch " + str(offset) + ": " + str(e)[:120])
    print(f"Completed batch; matches={len(rows)}, errors={len(errors)}", flush=True)
    time.sleep(0.2)
# Do not publish an empty snapshot, or pretend missing data is a zero-result day.
if not rows: raise RuntimeError("No price rows fetched; existing data remains untouched. " + "; ".join(errors[:3]))
latest_date = max(x["date"] for x in rows)
rows = [x for x in rows if x["date"] == latest_date]
snapshot = {"date":latest_date,"updatedAt":now.isoformat(),"universe":len(universe),
    "coverage":"best-effort unofficial Yahoo Finance daily prices",
    "notes":"Dividend yields and all-time highs are not yet available. Incomplete ticker coverage possible.",
    "stocks":rows,"errors":len(errors)}
OUT.write_text(json.dumps(snapshot,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
print(f"Saved {len(rows)} rows, universe {len(universe)}, errors {len(errors)}")
