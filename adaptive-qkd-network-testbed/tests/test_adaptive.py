import pandas as pd
import pytest

from qkd_lab.adaptive.actions import QKDAction, action_is_feasible
from qkd_lab.adaptive.features import validate_feature_columns
from qkd_lab.adaptive.policy import fit_empirical_policy


def test_mdi_capability_mask():
    a=QKDAction('mdi_qkd',0.4,0.1,0.8,10_000_000_000)
    assert not action_is_feasible(a, mdi_capable=False)
    assert action_is_feasible(a, mdi_capable=True)


def test_feature_leakage_rejected():
    with pytest.raises(ValueError):
        validate_feature_columns(['distance_km','true_y1'])


def test_policy_returns_abort_when_no_secure_rows():
    f=pd.DataFrame([{'distance_km':20.0,'action_name':'a','feasible':True,'abort':True,'service_utility':-1.0}])
    p=fit_empirical_policy(f,['distance_km'])
    assert p.select({'distance_km':20.0}) == 'ABORT'