"""recompute_den_trace() against FQResi's own createCorrArray (R), run on the
same trace and settings by tools/fqresi_reference.py: both standardisation
methods (before and from app 5.5), Linear and Ln equations, the sigmoid
NonLinear baseline, and a Resource FQResi doesn't know."""
import json
import warnings
from pathlib import Path

import numpy as np
import pytest

from imlresi import ResiResultSet
from imlresi.dotresi import ResiResult

DATA = Path(__file__).parent / 'data'
REF = json.loads((DATA / 'fqresi_reference.json').read_text())


@pytest.fixture(scope='module')
def drill():
    return ResiResultSet(DATA / 'corpus' / 'resi' / 'C03' / 'C03.Resi')[0].drill.astype(float)


def case_id(c):
    s = c['sData']
    return f"{s['Version'][-5:]}-{s['BaselineMethod']}-{s['Resource']}-{int(s['RPM'])}-{s['EqnType']}"


@pytest.mark.parametrize('case', REF['cases'], ids=case_id)
def test_matches_fqresi(drill, case):
    r = ResiResult(filename='x.rgp', descriptors=dict(case['sData']))
    r.drill = drill
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        got = r.recompute_den_trace({'a': -0.786, 'b': 1.0})
    assert len(got) == case['length']
    np.testing.assert_allclose(got[::REF['step']], case['den_every_25'], rtol=1e-12)
