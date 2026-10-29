"""Tests against the anonymised corpus of real data (tests/data/corpus).

- traces/Tnnn.*: real traces from the fq156 archive in every IML format,
  with Tnnn.expected.json, the archive's own parse of the same file.
- resi/Cnn/Cnn.Resi: real FWPA web-app project files (app versions 2.0 to
  5.6.0, cut down to <= 4 traces) with the source traces they were made from.

See manifest.json for what each case covers. tools/build_corpus.py rebuilds it.
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pytest
import rdata

from imlresi import ResiResultSet, Trace

CORPUS = Path(__file__).parent / 'data' / 'corpus'
MANIFEST = json.loads((CORPUS / 'manifest.json').read_text())
TRACES = [c for c in MANIFEST['cases'] if c['kind'] == 'trace']
RESI = [c for c in MANIFEST['cases'] if c['kind'] == 'resi']
RESI_READABLE = [c for c in RESI if c['rdata_loads']]

# archive rows whose stored parse wasn't made from these bytes (it went
# through the binary/txt conversion and has a different profile), so they
# can't serve as references
BAD_ARCHIVE_PARSE = {'T024', 'T032'}


def ids(cases):
    return [c['id'] for c in cases]


def read_raw(path):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return rdata.conversion.convert(rdata.parser.parse_file(str(path)))


def load_set(case):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return ResiResultSet(CORPUS / case['path'])


def test_manifest_matches_files():
    for c in MANIFEST['cases']:
        assert (CORPUS / c['path']).exists(), c['path']
    assert len(TRACES) >= 30 and len(RESI) >= 10


# --- traces ---------------------------------------------------------------

@pytest.mark.parametrize('case', TRACES, ids=ids(TRACES))
def test_trace_reads(case):
    t = Trace()
    t.read(CORPUS / case['path'])
    assert t.trace_format == case['format']
    assert len(t.drill) == case['n_drill']
    assert bool(t.feed is not None and len(t.feed)) == case['has_feed']
    t.to_json()
    t.hash()


@pytest.mark.parametrize('case', [c for c in TRACES if c['has_expected_json']], ids=lambda c: c['id'])
def test_trace_matches_archived_parse(case):
    if case['id'] in BAD_ARCHIVE_PARSE:
        pytest.skip('archived parse was not made from these bytes')
    t = Trace()
    t.read(CORPUS / case['path'])
    expected = json.loads((CORPUS / case['path']).with_suffix('.expected.json').read_text())
    got = t.to_dict()
    if t.trace_format not in ('json', 'pdc'):
        # the archive's conversion wrote these in mm; IML's JSON (and to_json()
        # since 0.0.46) has cm
        for k in ('depthMsmt', 'deviceLength'):
            assert expected['header'][k] == pytest.approx(got['header'][k] * 10)
            expected['header'][k] = got['header'][k]
    assert got['profile'] == expected['profile']
    diff = {k: (expected['header'].get(k), got['header'].get(k))
            for k in set(expected['header']) | set(got['header'])
            if expected['header'].get(k) != got['header'].get(k)}
    assert not diff
    assert got == expected


# --- .Resi files ----------------------------------------------------------

@pytest.mark.parametrize('case', RESI_READABLE, ids=ids(RESI_READABLE))
def test_resi_loads(case):
    rs = load_set(case)
    raw = read_raw(CORPUS / case['path'])
    assert len(rs) == case['n_traces'] == len(raw['df'])
    assert [r.FileName for r in rs] == list(raw['df']['FileName'])


@pytest.mark.parametrize('case', [c for c in RESI if not c['rdata_loads']], ids=lambda c: c['id'])
def test_unreadable_resi_fails_clearly(case):
    """Old Shiny-era files saved a reactivevalues object, which rdata can't parse."""
    with pytest.raises(ValueError):
        load_set(case)


@pytest.mark.parametrize('case', RESI_READABLE, ids=ids(RESI_READABLE))
def test_resi_traces_match_source_files(case):
    """Each stored resTrace is the drill profile of its source trace file."""
    rs = load_set(case)
    traces_dir = (CORPUS / case['path']).parent / 'traces'
    mismatched = []
    for r in rs:
        t = Trace()
        t.read(traces_dir / r.FileName)
        if not np.allclose(r.drill, t.drill):
            mismatched.append(r.FileName)
    if case['id'] in ('C09', 'C10'):
        pytest.xfail('stored resTraces differ from the source files in this old app version')
    assert not mismatched


DEN_CASES = [c for c in RESI_READABLE if 'denTraces' in c['nonempty_elements']]


@pytest.mark.parametrize('case', DEN_CASES, ids=ids(DEN_CASES))
def test_recomputed_density_matches_app(case):
    """recompute_den_trace() against the web app's own denTraces.

    Measured on 280 Dropbox files: exact for app 4.2.1 and 4.3.0, within
    0.3% for 4.2.4/4.5.1 (Linear baseline) and about 1.2% for the
    NonLinear baseline (5.0.0). The bound guards against regressions.
    """
    raw = read_raw(CORPUS / case['path'])
    names = [str(n) for n in raw['df']['FileName']]
    den = raw['denTraces'] if isinstance(raw['denTraces'], dict) else dict(zip(names, raw['denTraces']))
    checked = 0
    for r in load_set(case):
        stored = den.get(r.FileName)
        if stored is None:
            continue
        stored = np.ravel(np.asarray(stored, dtype=float))
        got = r.recompute_den_trace()
        assert len(got) == len(stored)
        rel = np.mean(np.abs(got - stored)) / np.mean(np.abs(stored))
        assert rel < 0.005, f'{r.FileName}: relative MAE {rel:.4f}'
        checked += 1
    assert checked
