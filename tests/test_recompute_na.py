"""The recompute_* functions must cope with missing and NA descriptors,
which is what .Resi files and DuckDB/Delta round trips actually contain."""
import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from imlresi import ResiResultSet

DATA = Path(__file__).parent / 'data'
NAS = [None, float('nan'), pd.NA, np.nan, 'NA', 'Not Available', '']
FIELDS = ['FeedSpeed', 'RPM', 'RPMCoef', 'DOB', 'BLCorrDen', 'BarkThickness', 'EntryRadius', 'UBDIA',
          'rSlope', 'rIntcpt', 'Standardised', 'Resource', 'ResiCode', 'Version', 'EqnType',
          'BaselineMethod', 'TraceType']


@pytest.fixture(scope='module')
def result():
    return ResiResultSet(DATA / '2_FWPA_4.8.0.Resi')[0]


def all_recomputes(r):
    return r.recompute_corr_trace(), r.recompute_den_trace(), r.recompute_cum_den_trace()


@pytest.mark.parametrize('na', NAS, ids=repr)
@pytest.mark.parametrize('field', FIELDS)
def test_na_descriptor(result, field, na):
    r = copy.deepcopy(result)
    r.descriptors[field] = na
    for arr in all_recomputes(r):
        assert arr is not None
        assert np.isfinite(arr).all(), f'{field}={na!r} produced non-finite values'


@pytest.mark.parametrize('field', FIELDS)
def test_missing_descriptor(result, field):
    r = copy.deepcopy(result)
    r.descriptors.pop(field, None)
    for arr in all_recomputes(r):
        assert np.isfinite(arr).all()


def test_na_same_as_missing(result):
    """An NA value should behave exactly like an absent one."""
    a, b = copy.deepcopy(result), copy.deepcopy(result)
    a.descriptors['BLCorrDen'] = pd.NA
    b.descriptors.pop('BLCorrDen')
    np.testing.assert_array_equal(a.recompute_den_trace(), b.recompute_den_trace())


@pytest.mark.parametrize('value, standardised', [
    (True, True), (False, False), ('TRUE', True), ('FALSE', False), ('F', False), ('0', False),
    (pd.NA, True), (None, True), (np.bool_(False), False),
])
def test_standardised_flag(result, value, standardised):
    r = copy.deepcopy(result)
    r.descriptors['Standardised'] = value
    assert r._is_standardised() is standardised
    raw = r.drill.astype(float)
    std = r._trace_standardise(raw)
    assert np.array_equal(std, raw) == (not standardised) or not standardised


@pytest.mark.parametrize('version, major', [
    ('Version 5.6.0', 5), ('Version 4.2.4', 4), ('Version 10.1.0', 10), ('', 0), (None, 0), (pd.NA, 0),
])
def test_version_major(result, version, major):
    r = copy.deepcopy(result)
    r.descriptors['Version'] = version
    assert r._version_major() == major


def test_v5_standardisation_selected(result):
    r4, r5 = copy.deepcopy(result), copy.deepcopy(result)
    r4.descriptors['Version'] = 'Version 4.5.1'
    r5.descriptors['Version'] = 'Version 5.6.0'
    for r in (r4, r5):
        r.descriptors.update({'FeedSpeed': 1000.0, 'RPM': 2500.0})
    assert not np.allclose(r4.recompute_corr_trace(), r5.recompute_corr_trace())
