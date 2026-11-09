"""All ratios use same-period statements; stock denominators are period-end."""
from app.schemas.domain import Statement, Metric


def divide(a: float | None, b: float | None, formula: str, evidence: list[str], positive_denominator: bool = True) -> Metric:
    valid = a is not None and b is not None and (b > 0 if positive_denominator else b != 0)
    return Metric(value=a / b if valid else None, formula=formula, evidence=evidence,
                  assumptions=['Period-end denominator; no industry calibration'],
                  limitation=None if valid else 'Missing input or nonpositive denominator')


def subtract(a, b):
    return None if a is None or b is None else a - b


def ratios(s: Statement, ref: str) -> dict[str, Metric]:
    definitions = {
        'current_ratio': (s.current_assets, s.current_liabilities, 'current_assets / current_liabilities'),
        'quick_ratio': (subtract(s.current_assets, s.inventory), s.current_liabilities, '(current_assets - inventory) / current_liabilities'),
        'debt_to_equity': (s.total_debt, s.equity, 'total_debt / equity'),
        'debt_to_assets': (s.total_debt, s.total_assets, 'total_debt / total_assets'),
        'gross_margin': (subtract(s.revenue, s.cost_of_goods), s.revenue, '(revenue - cost_of_goods) / revenue'),
        'operating_margin': (s.operating_income, s.revenue, 'operating_income / revenue'),
        'net_margin': (s.net_income, s.revenue, 'net_income / revenue'),
        'return_on_assets': (s.net_income, s.total_assets, 'net_income / period_end_total_assets'),
        'return_on_equity': (s.net_income, s.equity, 'net_income / period_end_equity'),
        'interest_coverage': (s.operating_income, s.interest_expense, 'operating_income / interest_expense'),
        'operating_cash_flow_ratio': (s.operating_cash_flow, s.current_liabilities, 'operating_cash_flow / current_liabilities'),
        'cash_ratio': (s.cash, s.current_liabilities, 'cash / current_liabilities'),
        'debt_service_coverage': (s.operating_cash_flow, s.annual_debt_service, 'operating_cash_flow / annual_debt_service'),
    }
    result = {name: divide(a, b, formula, [ref]) for name, (a, b, formula) in definitions.items()}
    result['working_capital'] = Metric(value=subtract(s.current_assets, s.current_liabilities), formula='current_assets - current_liabilities', unit=s.currency, evidence=[ref])
    return result
