"""Optional external adapter; no provider availability or timeliness is assumed."""
from datetime import date,datetime,timezone
from typing import Protocol
import re
from app.schemas.domain import Price,Provenance


class MarketProvider(Protocol):
    def history(self,symbol:str,start:date,end:date,currency:str) -> tuple[list[Price],Provenance]: ...


class YahooFinanceProvider:
    def history(self,symbol:str,start:date,end:date,currency:str):
        if not re.fullmatch(r'[A-Za-z0-9.^=\-]{1,20}',symbol) or start>=end or end>date.today():
            raise ValueError('Invalid symbol or date range')
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError('Install optional yfinance dependency to use this provider') from exc
        ticker=yf.Ticker(symbol)
        observed_currency=ticker.fast_info['currency']
        if observed_currency != currency:
            raise ValueError('Provider currency does not match requested currency')
        frame=ticker.history(start=start.isoformat(),end=end.isoformat(),auto_adjust=True,timeout=15)
        if frame.empty:
            raise ValueError('Provider returned no observations')
        prices=[Price(date=idx.date(),close=float(row['Close'])) for idx,row in frame.iterrows()]
        return prices,Provenance(provider='Yahoo Finance via yfinance',source=f'Yahoo Finance:{symbol}; adjusted close; end date exclusive',synthetic=False,currency=currency,retrieved_at=datetime.now(timezone.utc),quality='unverified')
