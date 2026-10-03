from datetime import date
from decimal import Decimal,ROUND_HALF_UP,localcontext
from sqlalchemy import or_,select
from sqlalchemy.orm import Session
from app.models import InvestmentTrade,PortfolioInstrumentMapping,PsxPriceObservation,TaxRule
CENT=Decimal("0.01");FOUR=Decimal("0.0001");ZERO=Decimal("0")
def money(v):return Decimal(v).quantize(CENT,rounding=ROUND_HALF_UP)
def replay(session:Session,user_id,as_of:date):
    trades=session.scalars(select(InvestmentTrade).where(InvestmentTrade.user_id==user_id,InvestmentTrade.trade_date<=as_of).order_by(InvestmentTrade.trade_date,InvestmentTrade.created_at,InvestmentTrade.id)).all();groups={}
    for t in trades:
        key=(t.investment_account_id,t.symbol);lots=groups.setdefault(key,[])
        if t.side=="BUY":lots.append({"trade_id":t.id,"date":t.trade_date,"quantity":Decimal(t.quantity),"cost":money(Decimal(t.gross_amount)+Decimal(t.fees))})
        else:
            remaining=Decimal(t.quantity)
            for lot in lots:
                if remaining<=0:break
                take=min(remaining,lot["quantity"]);part=lot["cost"] if take==lot["quantity"] else money(lot["cost"]*take/lot["quantity"]);lot["quantity"]-=take;lot["cost"]-=part;remaining-=take
    return {k:v for k,v in groups.items() if sum((x["quantity"] for x in v),ZERO)>0}
def positions(session,user,as_of:date,historical=False):
    if historical:source=replay(session,user.id,as_of)
    else:
        from app.routes_investments import holdings
        source={(h.investment_account_id,h.symbol):[{"trade_id":lot.buy_trade_id,"date":lot.acquired_on,"quantity":Decimal(lot.remaining_quantity),"cost":Decimal(lot.remaining_cost)} for lot in h.lots] for h in holdings(user,session)}
    result=[]
    mappings={(x.investment_account_id,x.holding_symbol):x for x in session.scalars(select(PortfolioInstrumentMapping).where(PortfolioInstrumentMapping.user_id==user.id)).all()}
    for (account_id,symbol),lots in source.items():
        quantity=sum((x["quantity"] for x in lots),ZERO);book=sum((x["cost"] for x in lots),ZERO);mapping=mappings.get((account_id,symbol));price=None
        if mapping:price=session.scalar(select(PsxPriceObservation).where(PsxPriceObservation.user_id==user.id,PsxPriceObservation.symbol==mapping.psx_symbol,PsxPriceObservation.adjustment_type=="raw",PsxPriceObservation.observation_date<=as_of).order_by(PsxPriceObservation.observation_date.desc()).limit(1))
        age=(as_of-price.observation_date).days if price else None;value=money(quantity*price.close_price) if price else None
        result.append({"investment_account_id":str(account_id),"holding_symbol":symbol,"quantity":str(quantity),"book_cost":str(money(book)),"lot_references":[{"trade_id":str(x["trade_id"]),"acquired_on":x["date"].isoformat(),"quantity":str(x["quantity"]),"book_cost":str(money(x["cost"]))} for x in lots if x["quantity"]>0],"mapping_id":str(mapping.id) if mapping else None,"psx_symbol":mapping.psx_symbol if mapping else None,"observed_price":str(price.close_price) if price else None,"observed_market_value":str(value) if value is not None else None,"unrealized_gain_loss":str(money(value-book)) if value is not None else None,"price_observation_id":str(price.id) if price else None,"price_source":price.source_name if price else None,"price_as_of":price.observation_date.isoformat() if price else None,"price_adjustment_type":"raw" if price else None,"price_verification":price.verification_status if price else None,"price_freshness":"fresh" if age is not None and age<=3 else "aging" if age is not None and age<=7 else "stale" if price else "missing","valuation_label":"last_observed_unverified" if price else "unavailable"})
    available=sum((Decimal(x["observed_market_value"]) for x in result if x["observed_market_value"] is not None),ZERO)
    total_book=sum((Decimal(x["book_cost"]) for x in result),ZERO)
    for x in result:x["position_weight_percent"]=str((Decimal(x["observed_market_value"])/available*100).quantize(FOUR,rounding=ROUND_HALF_UP)) if x["observed_market_value"] is not None and available else None
    weights=[Decimal(x["position_weight_percent"])/100 for x in result if x["position_weight_percent"]]
    return result,{"book_cost":str(money(total_book)),"observed_market_value":str(money(available)) if available else None,"unavailable_positions":sum(x["observed_market_value"] is None for x in result),"largest_position_weight_percent":str((max(weights)*100).quantize(FOUR)) if weights else None,"concentration_hhi":str(sum((x*x for x in weights),ZERO).quantize(FOUR)) if weights else None}
def adjusted_risk(session,user_id,symbol,as_of,lookback=30):
    rows=session.scalars(select(PsxPriceObservation).where(PsxPriceObservation.user_id==user_id,PsxPriceObservation.symbol==symbol,PsxPriceObservation.adjustment_type=="adjusted",PsxPriceObservation.observation_date<=as_of).order_by(PsxPriceObservation.observation_date)).all()
    if len(rows)<2:return {"available":False,"reason":"At least two adjusted observations are required.","observation_ids":[str(x.id) for x in rows]}
    if len({x.source_name for x in rows})!=1:return {"available":False,"reason":"Adjusted observations have conflicting sources; select a consistent authorized series.","observation_ids":[str(x.id) for x in rows]}
    rows=rows[-lookback:];closes=[Decimal(x.close_price) for x in rows];returns=[closes[i]/closes[i-1]-1 for i in range(1,len(closes))];mean=sum(returns)/Decimal(len(returns));vol=None
    if len(returns)>=2:
        variance=sum((x-mean)**2 for x in returns)/Decimal(len(returns)-1)
        with localcontext() as c:c.prec=28;vol=variance.sqrt()*Decimal(252).sqrt()*100
    peak=closes[0];draw=ZERO
    for close in closes:peak=max(peak,close);draw=min(draw,close/peak-1)
    q=lambda x:str(x.quantize(FOUR,rounding=ROUND_HALF_UP)) if x is not None else None
    return {"available":True,"period_return_percent":q((closes[-1]/closes[0]-1)*100),"annualized_volatility_percent":q(vol),"maximum_drawdown_percent":q(draw*100),"window_observations":len(rows),"observation_ids":[str(x.id) for x in rows],"source_dates":[x.observation_date.isoformat() for x in rows],"sources":sorted({x.source_name for x in rows}),"adjustment_type":"adjusted","formulas":{"return":"(last adjusted close / first adjusted close - 1) × 100","volatility":"sample standard deviation of adjusted close returns × sqrt(252) × 100","maximum_drawdown":"minimum(adjusted close / prior running peak - 1) × 100"}}
def sale_estimate(session,user,account_id,symbol,quantity,fees,as_of,historical=False):
    if historical:lots=replay(session,user.id,as_of).get((account_id,symbol),[])
    else:
        from app.routes_investments import fifo_plan
        lots=[{"trade_id":lot.buy_trade_id,"date":lot.acquired_on,"quantity":qty,"cost":cost} for lot,qty,cost in fifo_plan(session,user.id,account_id,symbol,quantity,as_of)]
    available=sum((x["quantity"] for x in lots),ZERO)
    if available<quantity:raise ValueError("Insufficient historical quantity")
    remaining=quantity;cost=ZERO;refs=[]
    for lot in lots:
        if remaining<=0:break
        take=min(remaining,lot["quantity"]);part=lot["cost"] if take==lot["quantity"] else money(lot["cost"]*take/lot["quantity"]);cost+=part;remaining-=take;refs.append({"trade_id":str(lot["trade_id"]),"quantity":str(take),"cost_basis":str(part)})
    mapping=session.scalar(select(PortfolioInstrumentMapping).where(PortfolioInstrumentMapping.user_id==user.id,PortfolioInstrumentMapping.investment_account_id==account_id,PortfolioInstrumentMapping.holding_symbol==symbol))
    price=session.scalar(select(PsxPriceObservation).where(PsxPriceObservation.user_id==user.id,PsxPriceObservation.symbol==mapping.psx_symbol,PsxPriceObservation.adjustment_type=="raw",PsxPriceObservation.observation_date<=as_of).order_by(PsxPriceObservation.observation_date.desc()).limit(1)) if mapping else None
    if not price:return {"available":False,"missing_inputs":["confirmed mapping or raw closing price"],"quantity":str(quantity),"fees":str(fees),"hypothetical":True}
    gross=money(quantity*price.close_price);gain=gross-money(fees)-cost;rule=session.scalar(select(TaxRule).where(TaxRule.user_id==user.id,TaxRule.effective_from<=as_of,or_(TaxRule.effective_to.is_(None),TaxRule.effective_to>=as_of)).order_by(TaxRule.effective_from.desc(),TaxRule.created_at.desc()).limit(1));tax=None
    if rule:tax=money(max(gain,ZERO)*rule.gain_tax_rate/Decimal(100))
    tax_status=("configured_gain_estimate" if gain>ZERO else "configured_no_automatic_loss_credit") if rule else "not_configured"
    return {"available":True,"quantity":str(quantity),"price":str(price.close_price),"price_observation_id":str(price.id),"price_source":price.source_name,"price_as_of":price.observation_date.isoformat(),"gross_proceeds":str(gross),"estimated_fees":str(money(fees)),"fifo_cost_basis":str(money(cost)),"taxable_gain_loss":str(money(gain)),"estimated_tax":str(tax) if tax is not None else None,"tax_status":tax_status,"tax_rule_id":str(rule.id) if rule else None,"tax_rate":str(rule.gain_tax_rate) if rule else None,"net_proceeds":str(gross-money(fees)-(tax or ZERO)),"fifo_allocations":refs,"hypothetical":True,"financial_records_changed":False,"limitations":["Observed raw close is not a live executable quote.","No order, ledger entry, lot consumption, or holding mutation occurred.","Unrepresented broker charges, withholding, liquidity, and slippage are excluded."]}
