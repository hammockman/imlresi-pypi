"""Delta Lake merges must add to an existing table, never replace it."""
import pytest

deltalake = pytest.importorskip('deltalake')
from deltalake import DeltaTable

from imlresi.dotresi import ResiResult, ResiResultSet


def make_set(*names, tree='T'):
    rs = ResiResultSet()
    for n in names:
        rs.results.append(ResiResult(n, descriptors={'FileName': n, 'TreeID': f'{tree}-{n}', 'UBDIA': 1.0}))
    return rs


def file_names(path):
    return sorted(DeltaTable(str(path)).to_pandas()['FileName'])


@pytest.fixture
def seeded(tmp_path):
    path = tmp_path / 'tbl'
    make_set('a', 'b', 'c').to_deltalake(path, mode='merge')
    assert file_names(path) == ['a', 'b', 'c']
    return path


@pytest.mark.parametrize('target', ['path', 'str', 'file_uri', 'deltatable'])
def test_merge_keeps_existing_rows(seeded, target):
    to = {
        'path': lambda: seeded,
        'str': lambda: str(seeded),
        'file_uri': lambda: seeded.as_uri(),
        'deltatable': lambda: DeltaTable(str(seeded)),
    }[target]()
    res = make_set('c', 'z', tree='U').to_deltalake(to, mode='merge')
    assert file_names(seeded) == ['a', 'b', 'c', 'z']
    assert (res.num_inserted, res.num_updated) == (1, 1)
    df = DeltaTable(str(seeded)).to_pandas().set_index('FileName')
    assert df.loc['c', 'TreeID'] == 'U-c'
    assert df.loc['a', 'TreeID'] == 'T-a'


@pytest.mark.parametrize('target', ['path', 'deltatable'])
def test_append_keeps_existing_rows(seeded, target):
    to = seeded if target == 'path' else DeltaTable(str(seeded))
    make_set('z').to_deltalake(to, mode='append')
    assert file_names(seeded) == ['a', 'b', 'c', 'z']


def test_overwrite_replaces(seeded):
    make_set('z').to_deltalake(seeded, mode='overwrite')
    assert file_names(seeded) == ['z']


def test_merge_creates_missing_table(tmp_path):
    path = tmp_path / 'new'
    res = make_set('a').to_deltalake(path.as_uri(), mode='merge')
    assert file_names(path) == ['a']
    assert res.num_inserted == 1


def test_merge_does_not_replace_non_delta_dir(tmp_path):
    """A directory that isn't a Delta table must not be silently clobbered."""
    path = tmp_path / 'not_delta'
    path.mkdir()
    (path / 'keep.txt').write_text('precious')
    try:
        make_set('a').to_deltalake(path, mode='merge')
    except Exception:
        pass
    assert (path / 'keep.txt').read_text() == 'precious'


@pytest.mark.parametrize('key', ['nope', 'FileName = source.FileName OR 1=1', ['FileName', 'nope'], []])
def test_merge_key_must_be_a_column(seeded, key):
    with pytest.raises(ValueError):
        make_set('z').to_deltalake(seeded, mode='merge', merge_key=key)
    assert file_names(seeded) == ['a', 'b', 'c']


def test_compound_merge_key(seeded):
    make_set('a', 'q', tree='T').to_deltalake(seeded, mode='merge', merge_key=['FileName', 'TreeID'])
    assert file_names(seeded) == ['a', 'b', 'c', 'q']
