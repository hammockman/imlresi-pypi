"""Check ResiResultSet against the raw contents of real .Resi files.

The files in tests/data were written by the FWPA web app (FQResi) and by
HQPAPI, so their raw R objects are the reference: whatever the library
reads, or writes back, should agree with them.
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rdata

from imlresi import ResiResultSet

DATA = Path(__file__).parent / 'data'
SAMPLES = sorted(DATA.glob('*.Resi'))


def read_raw(path):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return rdata.conversion.convert(rdata.parser.parse_file(str(path)))


def as_float_or_none(v):
    return None if v is None or pd.isna(v) else float(v)


@pytest.fixture(params=SAMPLES, ids=lambda p: p.name)
def sample(request):
    path = request.param
    return path, read_raw(path), ResiResultSet(path)


def test_samples_present():
    assert len(SAMPLES) == 4


def test_one_result_per_df_row(sample):
    _, raw, rs = sample
    assert len(rs) == len(raw['df'])
    assert [r.FileName for r in rs] == list(raw['df']['FileName'])


def test_dob_preserved(sample):
    _, raw, rs = sample
    df = raw['df']
    assert 'DOB' in df.columns
    assert df['DOB'].notna().all(), 'sample should have real DOB values'
    for r, expected in zip(rs, df['DOB']):
        assert r.DOB == pytest.approx(float(expected))


def test_dbhob_kept_separately(sample):
    _, raw, rs = sample
    df = raw['df']
    if 'DBHOB' not in df.columns:
        pytest.skip('no DBHOB column')
    for r, expected in zip(rs, df['DBHOB']):
        assert as_float_or_none(r.get_descriptor('DBHOB')) == as_float_or_none(expected)
        # DOB must not be taken from the (usually NA) DBHOB column
        assert r.DOB is not None


def test_dbhob_used_when_dob_missing():
    from imlresi.dotresi import ResiResult
    r = ResiResult('a.rgp', descriptors={'FileName': 'a.rgp', 'DBHOB': 250.0})
    assert r.DOB == 250.0
    assert r.get_descriptor('DOB') == 250.0


def test_dob_falls_back_to_dbhob_on_load(tmp_path):
    """A file with only DBHOB (older layout) still yields DOB."""
    from imlresi.dotresi import ResiResult
    src = ResiResultSet(SAMPLES[0])
    rs = ResiResultSet()
    for r in src:
        d = {k: v for k, v in r.descriptors.items() if k not in ('DOB', 'DBHOB')}
        d['DBHOB'] = r.DOB
        rs.results.append(ResiResult(r.FileName, descriptors=d, drill=r.drill, feed=r.feed))
    out = tmp_path / 'dbhob_only.Resi'
    rs.to_dotresi(out, format_version='4.2.4', overwrite=True)
    df = read_raw(out)['df']
    assert 'DBHOB' in df.columns
    back = ResiResultSet(out)
    for a, b in zip(src, back):
        assert b.DOB == pytest.approx(a.DOB)


def test_compact_sequence_bomb_is_refused(tmp_path):
    # 1:2e9 saved by R is stored as its two ends: ~200 bytes asking for 8 GB
    import imlresi.dotresi as d
    src = Path(__file__).parent / 'data' / 'hostile' / 'altrep_bomb.Resi'
    with pytest.raises(ValueError, match='compact R sequence'):
        d.ResiResultSet(src)


def test_decompression_bomb_is_refused(tmp_path, monkeypatch):
    import gzip
    import imlresi.dotresi as d
    src = Path(__file__).parent / 'data' / 'corpus' / 'resi' / 'C03' / 'C03.Resi'
    monkeypatch.setattr(d, 'MAX_RESI_BYTES', 200_000)
    assert src.stat().st_size < 200_000 < len(gzip.decompress(src.read_bytes()))
    with pytest.raises(ValueError, match='decompressed'):
        d.ResiResultSet(src)


def test_parse_limit_leaves_real_files_alone():
    from imlresi.dotresi import parse_rds
    for p in sorted((Path(__file__).parent / 'data' / 'corpus' / 'resi').glob('C*/C*.Resi')):
        if p.parent.name != 'C12':  # unreadable by rdata anyway
            assert parse_rds(p) is not None
