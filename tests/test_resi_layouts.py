"""Writing .Resi files in the web app's real layouts, and round trips of real files."""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rdata

from imlresi import ResiResultSet, change_instrument_id
from imlresi.dotresi import RESI_LAYOUTS, resi_layout

CORPUS = Path(__file__).parent / 'data' / 'corpus'
MANIFEST = json.loads((CORPUS / 'manifest.json').read_text())
RESI = [c for c in MANIFEST['cases'] if c['kind'] == 'resi' and c['rdata_loads']]
DATA = Path(__file__).parent / 'data'
SAMPLES = sorted(DATA.glob('*.Resi')) + [CORPUS / c['path'] for c in RESI]


def read_raw(path):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return rdata.conversion.convert(rdata.parser.parse_file(str(path)))


def load(path):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return ResiResultSet(path)


def assert_frame_same(a, b):
    assert list(a.columns) == list(b.columns)
    for c in a.columns:
        assert str(a[c].dtype) == str(b[c].dtype), c
        pd.testing.assert_series_equal(a[c].reset_index(drop=True), b[c].reset_index(drop=True), check_names=False)


def assert_version_same(a, b):
    if isinstance(a, dict):
        assert isinstance(b, dict) and list(a) == list(b)
        for k in a:
            np.testing.assert_array_equal(a[k], b[k])
    else:
        np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize('path', SAMPLES, ids=lambda p: p.name)
def test_round_trip_keeps_df_exactly(tmp_path, path):
    out = tmp_path / 'rt.Resi'
    load(path).to_dotresi(out)
    a, b = read_raw(path), read_raw(out)
    assert_frame_same(a['df'], b['df'])
    if a.get('version') is not None:
        assert_version_same(a['version'], b['version'])
    for key in ('resTraces', 'feedTraces'):
        if a.get(key):
            names = list(a['df']['FileName'])
            src = a[key] if isinstance(a[key], dict) else dict(zip(names, a[key]))
            for n in names:
                v = src.get(n)
                if v is not None and not isinstance(v, list) and np.size(v):
                    np.testing.assert_allclose(np.ravel(b[key][n]), np.ravel(v))


@pytest.mark.parametrize('path', SAMPLES, ids=lambda p: p.name)
def test_round_trip_twice_is_stable(tmp_path, path):
    one, two = tmp_path / '1.Resi', tmp_path / '2.Resi'
    load(path).to_dotresi(one)
    load(one).to_dotresi(two)
    assert_frame_same(read_raw(one)['df'], read_raw(two)['df'])


@pytest.mark.parametrize('layout', sorted(RESI_LAYOUTS))
@pytest.mark.parametrize('path', SAMPLES, ids=lambda p: p.name)
def test_convert_to_layout(tmp_path, path, layout):
    out = tmp_path / 'conv.Resi'
    src = load(path)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        src.to_dotresi(out, format_version=layout)
    raw = read_raw(out)
    df = raw['df']
    assert list(df.columns) == list(RESI_LAYOUTS[layout])
    for c, t in RESI_LAYOUTS[layout].items():
        assert str(df[c].dtype) == t, c
    if layout == '4.2.4':
        assert str(raw['version'][0]) == 'Version 4.2.4'
    elif layout == '4.5.1':
        assert str(raw['version'][0]) == 'Version 4.5.1'
    else:
        assert isinstance(raw['version'], dict) and 'platform' in raw['version']
        assert set(df['Version']) <= {'Version 5.6.0'} | {str(r.get_descriptor('Version')) for r in src}
    back = load(out)
    for a, b in zip(src, back):
        assert b.FileName == a.FileName
        assert b.DOB == pytest.approx(a.DOB) if a.DOB is not None else True
        assert b.get_descriptor('FeedSpeed') == pytest.approx(a.get_descriptor('FeedSpeed'))
        assert b.SampleDate == a.SampleDate
        for col in ('UBDIA', 'BarkThickness', 'PrMOE', 'OWDensity', 'rSlope', 'rIntcpt'):
            if col in RESI_LAYOUTS[layout] and a.get_descriptor(col) is not None:
                assert b.get_descriptor(col) == pytest.approx(a.get_descriptor(col)), col


def test_conversion_warns_about_dropped_columns(tmp_path):
    src = load(CORPUS / 'resi' / 'C06' / 'C06.Resi')  # 5.6.0, has MOEmodel etc.
    with pytest.warns(UserWarning, match='MOEmodel'):
        src.to_dotresi(tmp_path / 'x.Resi', format_version='4.2.4')


def test_edited_value_is_written(tmp_path):
    src = load(CORPUS / 'resi' / 'C03' / 'C03.Resi')  # 4.2.4: FeedSpeed is text
    src[0].descriptors['FeedSpeed'] = 1500.0
    src[0].descriptors['TreeID'] = 'EDITED'
    out = tmp_path / 'e.Resi'
    src.to_dotresi(out)
    df = read_raw(out)['df']
    assert df['FeedSpeed'][0] == '1500'
    assert df['TreeID'][0] == 'EDITED'
    assert_frame_same(df.iloc[1:], read_raw(CORPUS / 'resi' / 'C03' / 'C03.Resi')['df'].iloc[1:])


def test_new_results_use_latest_layout(tmp_path):
    from imlresi import Trace, save_traces_to_dotresi
    t = Trace()
    t.read(DATA / '2-178-withfeed.pdc')
    out = tmp_path / 'n.Resi'
    save_traces_to_dotresi([t], out, format_version='latest')
    assert list(read_raw(out)['df'].columns) == list(RESI_LAYOUTS['5.6.0'])


def test_mixed_sources_need_a_layout(tmp_path):
    a = load(CORPUS / 'resi' / 'C03' / 'C03.Resi')   # 4.2.4
    b = load(CORPUS / 'resi' / 'C06' / 'C06.Resi')   # 5.6.0
    a.results += b.results
    a.source_layouts.update(b.source_layouts)
    out = tmp_path / 'mixed.Resi'
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        a.to_dotresi(out)
    assert list(read_raw(out)['df'].columns) == list(RESI_LAYOUTS['5.6.0'])


@pytest.mark.parametrize('case', ['C03', 'C05', 'C06'])
def test_change_instrument_id_keeps_layout(tmp_path, case):
    src = CORPUS / 'resi' / case / f'{case}.Resi'
    out = tmp_path / 'id.Resi'
    change_instrument_id(src, 'PD500-9999', output_filepath=out)
    a, b = read_raw(src)['df'], read_raw(out)['df']
    assert list(a.columns) == list(b.columns)
    assert set(b['ResiCode']) == {'PD500-9999'}
    assert_frame_same(a.drop(columns='ResiCode'), b.drop(columns='ResiCode'))


@pytest.mark.parametrize('name, canonical', [
    ('4.2.4', '4.2.4'), ('legacy', '4.2.4'), ('4.5.1', '4.5.1'), ('4.8.0', '5.6.0'), ('latest', '5.6.0'), ('5.6.0', '5.6.0'),
])
def test_layout_names(name, canonical):
    assert resi_layout(name) == canonical


def test_unknown_layout():
    with pytest.raises(ValueError):
        resi_layout('9.9')


def test_no_feed_is_none_not_nan():
    """C01 stores feedTraces as NULL / list(NULL): there is no feed."""
    for r in load(CORPUS / 'resi' / 'C01' / 'C01.Resi'):
        assert r.feed is None
