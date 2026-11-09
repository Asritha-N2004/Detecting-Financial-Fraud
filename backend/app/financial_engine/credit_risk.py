"""No production default probability is emitted without a calibrated artifact."""
from app.schemas.domain import Statement, Metric
from app.financial_engine.ratios import divide, subtract


def altman_z(s: Statement, public_manufacturer: bool, ref: str) -> Metric:
    formula = '1.2*(CA-CL)/A + 1.4*RE/A + 3.3*EBIT/A + 0.6*MVE/L + Revenue/A'
    if not public_manufacturer:
        return Metric(value=None, formula=formula, limitation='Original Altman Z model restricted here to listed manufacturing companies')
    components = [divide(subtract(s.current_assets,s.current_liabilities),s.total_assets,'WC/A',[ref]), divide(s.retained_earnings,s.total_assets,'RE/A',[ref]), divide(s.operating_income,s.total_assets,'EBIT/A',[ref]), divide(s.market_equity,s.total_liabilities,'MVE/L',[ref]), divide(s.revenue,s.total_assets,'Revenue/A',[ref])]
    valid = all(x.value is not None for x in components)
    return Metric(value=sum(w*x.value for w,x in zip([1.2,1.4,3.3,.6,1],components)) if valid else None, formula=formula, evidence=[ref], assumptions=['Original public manufacturing coefficients; historical distress indicator, not PD'], limitation=None if valid else 'Missing or invalid Altman inputs')


def train_logistic_baseline(features, labels, seed: int = 7):
    """Research-only baseline; caller must independently calibrate before serving PD."""
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    model = make_pipeline(StandardScaler(), LogisticRegression(random_state=seed, max_iter=1000))
    return model.fit(features, labels)
