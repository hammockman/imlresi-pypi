"""Trace and result objects must survive copy, deepcopy and pickle
(multiprocessing and Spark workers pickle them)."""
import copy
import pickle
from pathlib import Path

import numpy as np
import pytest

from imlresi import ResiResultSet, Trace

DATA = Path(__file__).parent / 'data'
TRACE_FILES = ['1-131-withfeed-json.rgp', '1-131-withfeed.rgp', '1-131-withfeed-txt1.txt',
               '1-131-withfeed-txt2.txt', '2-178-withfeed.pdc']
COPIERS = {
    'copy': copy.copy,
    'deepcopy': copy.deepcopy,
    'pickle': lambda o: pickle.loads(pickle.dumps(o)),
}


@pytest.mark.parametrize('how', COPIERS)
@pytest.mark.parametrize('fn', TRACE_FILES)
def test_trace_copies(fn, how):
    tr = Trace()
    tr.read(DATA / fn)
    tr._res = {'TraceType': 'B-B', 'UBDIA': 6.0}
    c = COPIERS[how](tr)
    assert c.to_json() == tr.to_json()
    assert c.get_ubdia() == 6.0
    assert c.trace_filename == tr.trace_filename


@pytest.mark.parametrize('how', COPIERS)
def test_unread_trace_copies(how):
    c = COPIERS[how](Trace())
    assert c.drill == [] and c._res is None


@pytest.mark.parametrize('how', COPIERS)
def test_resi_result_set_copies(how):
    rs = ResiResultSet(DATA / '2_FWPA_4.8.0.Resi')
    c = COPIERS[how](rs)
    assert len(c) == len(rs)
    for a, b in zip(rs, c):
        assert b.descriptors.keys() == a.descriptors.keys()
        np.testing.assert_array_equal(b.drill, a.drill)
        assert b.DOB == a.DOB


def test_result_pickles_through_multiprocessing():
    import multiprocessing as mp
    rs = ResiResultSet(DATA / '2_FWPA_4.8.0.Resi')
    with mp.get_context('spawn').Pool(1) as pool:
        names = pool.map(_file_name, list(rs))
    assert names == [r.FileName for r in rs]


def _file_name(r):
    return r.FileName


def test_private_attribute_lookups_fail_normally():
    tr = Trace()
    with pytest.raises(AttributeError):
        tr._nope
    with pytest.raises(AttributeError):
        tr.__nope__
    r = ResiResultSet(DATA / '2_FWPA_4.8.0.Resi')[0]
    with pytest.raises(AttributeError):
        r._nope
    assert not hasattr(r, 'trace')


def test_mistyped_getter_fails_after_processing():
    tr = Trace()
    tr.read(DATA / '2-178-withfeed.pdc')
    tr._res = {'UBDIA': 6.0}
    assert tr.get_ubdia() == 6.0
    assert tr.get_UBDIA() == 6.0
    with pytest.raises(AttributeError):
        tr.get_ubdai()
    # real methods are unaffected
    assert tr.get_feedspeed() == 200


def test_getter_before_processing_warns_and_returns_none():
    tr = Trace()
    tr.read(DATA / '2-178-withfeed.pdc')
    assert tr.get_ubdia() is None
