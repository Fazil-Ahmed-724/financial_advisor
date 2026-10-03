import re
from datetime import date
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP,localcontext

Q=Decimal("0.0001");SYMBOL=re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,19}$")
def money(value):
    d=Decimal(str(value))
    if not d.is_finite() or d<=0 or d.as_tuple().exponent < -4:raise ValueError("must be positive with at most four decimals")
    return d.quantize(Q)
def normalize(row,source):
    errors=[];warnings=[];data={}
    try:
        data["symbol"]=str(row.get("symbol","")).strip().upper()
        if not SYMBOL.fullmatch(data["symbol"]):errors.append("symbol must contain 1-20 uppercase letters, numbers, dots, or hyphens")
        data["observation_date"]=date.fromisoformat(str(row.get("observation_date",""))).isoformat()
        for key in ("open","high","low","close"):data[key]=str(money(row.get(key,"")))
        data["volume"]=int(str(row.get("volume","")))
        if data["volume"]<0:errors.append("volume must be nonnegative")
        data["currency"]=str(row.get("currency","")).upper()
        if data["currency"]!="PKR":errors.append("currency must be PKR")
        data["source"]=str(row.get("source") or source).strip()
        if not data["source"]:errors.append("source is required")
        data["adjustment_type"]=str(row.get("adjustment_type","")).lower()
        if data["adjustment_type"] not in ("raw","adjusted"):errors.append("adjustment_type must be raw or adjusted")
        if not errors:
            o,h,l,c=map(Decimal,(data["open"],data["high"],data["low"],data["close"]))
            if h<max(o,c,l) or l>min(o,c,h):errors.append("OHLC values are inconsistent")
    except (ValueError,InvalidOperation,TypeError):errors.append("date, prices, and volume must use valid documented formats")
    return data,errors,warnings
def analyze(rows,lookback=14,as_of=None):
    ordered=sorted(rows,key=lambda x:x.observation_date)
    if as_of:ordered=[x for x in ordered if x.observation_date<=as_of]
    if len(ordered)<2:raise ValueError("at least two chronological observations are required")
    closes=[Decimal(x.close_price) for x in ordered];rets=[closes[i]/closes[i-1]-1 for i in range(1,len(closes))]
    period=(closes[-1]/closes[0]-1)*100
    sample=rets[-lookback:];vol=None
    if len(sample)>=2:
        mean=sum(sample)/Decimal(len(sample));variance=sum((x-mean)**2 for x in sample)/Decimal(len(sample)-1)
        with localcontext() as ctx:ctx.prec=28;vol=variance.sqrt()*Decimal(252).sqrt()*100
    window=closes[-lookback:];ma=sum(window)/Decimal(len(window)) if len(window)>=lookback else None
    rsi=None
    if len(rets)>=lookback:
        changes=[closes[i]-closes[i-1] for i in range(len(closes)-lookback,len(closes))]
        gains=sum(max(x,Decimal(0)) for x in changes)/Decimal(lookback);losses=sum(max(-x,Decimal(0)) for x in changes)/Decimal(lookback)
        rsi=Decimal(100) if losses==0 else Decimal(100)-(Decimal(100)/(Decimal(1)+gains/losses))
    gaps=[(ordered[i].observation_date-ordered[i-1].observation_date).days for i in range(1,len(ordered)) if (ordered[i].observation_date-ordered[i-1].observation_date).days>4]
    q=lambda x:str(x.quantize(Q,rounding=ROUND_HALF_UP)) if x is not None else None
    return {"symbol":ordered[0].symbol,"as_of_date":ordered[-1].observation_date.isoformat(),"start_date":ordered[0].observation_date.isoformat(),"observation_count":len(ordered),"period_return_percent":q(period),"annualized_rolling_volatility_percent":q(vol),"moving_average":q(ma),"rsi":q(rsi),"lookback":lookback,"observation_ids":[str(x.id) for x in ordered],"source_dates":[x.observation_date.isoformat() for x in ordered],"adjustment_types":sorted({x.adjustment_type for x in ordered}),"sources":sorted({x.source_name for x in ordered}),"verification_status":"unverified","freshness":"stale" if (date.today()-ordered[-1].observation_date).days>7 else "fresh","gap_days":gaps,"hypothetical":True,"formulas":{"period_return":"(last close / first close - 1) × 100","volatility":"sample standard deviation of daily close returns × sqrt(252) × 100","moving_average":f"arithmetic mean of the last {lookback} closes; unavailable with fewer observations","rsi":f"simple average gains/losses over {lookback} chronological closes; unavailable with fewer observations"},"limitations":["No look-ahead: observations after as_of_date are excluded.","Fees, taxes, liquidity, survivorship bias, and unrepresented corporate actions are excluded.","Historical evidence is not a prediction, recommendation, or suitability determination."]}
