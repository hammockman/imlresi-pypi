"""Writing .Resi files: appending traces and changing the instrument ID."""
from pathlib import Path

import pytest
import rdata

from imlresi import ResiResultSet, Trace, change_instrument_id, save_traces_to_dotresi

DATA = Path(__file__).parent / 'data'
TRACES = ['2-178-withfeed.pdc', '7-561_COOCHI_203_H_01M103.pdc', '1-131-withfeed-json.rgp']


def read_raw(path):
    return rdata.conversion.convert(rdata.parser.parse_file(str(path)))


def load_trace(name):
    t = Trace()
    t.read(DATA / name)
    return t


def assert_consistent(raw):
    names = list(raw['df']['FileName'])
    assert len(names) == len(set(names)), 'duplicate FileName rows'
    assert set(raw['resTraces']) == set(names)


def test_tree_id_comes_from_id_number(tmp_path):
    t = load_trace('7-561_COOCHI_203_H_01M103.pdc')
    out = tmp_path / 'a.Resi'
    save_traces_to_dotresi([t], out)
    df = read_raw(out)['df']
    assert df['TreeID'][0] == t.get_resiId()
    assert df['TreeID'][0] != t.get_remark() or t.get_remark() == t.get_resiId()


def test_append_adds_new_traces(tmp_path):
    out = tmp_path / 'a.Resi'
    save_traces_to_dotresi([load_trace(TRACES[0])], out)
    save_traces_to_dotresi([load_trace(TRACES[1]), load_trace(TRACES[2])], out)
    raw = read_raw(out)
    assert sorted(raw['df']['FileName']) == sorted(TRACES)
    assert_consistent(raw)


def test_append_same_trace_replaces(tmp_path):
    out = tmp_path / 'a.Resi'
    save_traces_to_dotresi([load_trace(TRACES[0]), load_trace(TRACES[1])], out)
    with pytest.warns(UserWarning, match='Replacing'):
        save_traces_to_dotresi([load_trace(TRACES[0])], out)
    raw = read_raw(out)
    assert sorted(raw['df']['FileName']) == sorted(TRACES[:2])
    assert_consistent(raw)


def test_duplicate_within_one_call(tmp_path):
    out = tmp_path / 'a.Resi'
    with pytest.warns(UserWarning, match='Replacing'):
        save_traces_to_dotresi([load_trace(TRACES[0]), load_trace(TRACES[0])], out)
    assert_consistent(read_raw(out))


def test_append_false_starts_fresh(tmp_path):
    out = tmp_path / 'a.Resi'
    save_traces_to_dotresi([load_trace(TRACES[0])], out)
    save_traces_to_dotresi([load_trace(TRACES[1])], out, append=False)
    assert list(read_raw(out)['df']['FileName']) == [TRACES[1]]


@pytest.mark.parametrize('sample', ['2_FWPA_4.8.0.Resi', '2_HQPAPI_4.2.4.Resi'])
def test_change_instrument_id_everywhere(tmp_path, sample):
    out = tmp_path / 'changed.Resi'
    change_instrument_id(DATA / sample, 'PD500-9999', output_filepath=out,
                         format_version='4.2.4' if '4.2.4' in sample else '4.8.0')
    raw = read_raw(out)
    assert set(raw['df']['ResiCode']) == {'PD500-9999'}
    ring = raw.get('ringData')
    if ring is not None and len(ring) and 'ResiCode' in ring.columns:
        assert set(ring['ResiCode']) == {'PD500-9999'}
    for r in ResiResultSet(out):
        assert r.ResiCode == 'PD500-9999'
        for row in r.ring_data:
            assert row.get('ResiCode', 'PD500-9999') == 'PD500-9999'


def test_set_instrument_id_in_memory():
    rs = ResiResultSet(DATA / '2_FWPA_4.8.0.Resi')
    assert any(row.get('ResiCode') for r in rs for row in r.ring_data), 'sample should have ringData'
    rs.set_instrument_id('PD400-1234')
    for r in rs:
        assert r.ResiCode == 'PD400-1234'
        assert all(row.get('ResiCode') == 'PD400-1234' for row in r.ring_data if 'ResiCode' in row)
