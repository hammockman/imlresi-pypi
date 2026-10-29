"""DuckDB export/import: round trips on real samples, identifier safety, rollback."""
from pathlib import Path

import duckdb
import numpy as np
import pytest

from imlresi import ResiResultSet
from imlresi.dotresi import duckdb_table_names

DATA = Path(__file__).parent / 'data'
SAMPLE = DATA / '2_FWPA_4.8.0.Resi'


@pytest.fixture
def conn():
    c = duckdb.connect(':memory:')
    yield c
    c.close()


@pytest.mark.parametrize('prefix', ['', 'proj_', 'P2026_'])
def test_roundtrip_real_sample(conn, prefix):
    src = ResiResultSet(SAMPLE)
    src.to_duckdb(conn, table_prefix=prefix)
    back = ResiResultSet.from_duckdb(conn, table_prefix=prefix)
    assert sorted(r.FileName for r in back) == sorted(r.FileName for r in src)
    by_name = {r.FileName: r for r in back}
    for r in src:
        b = by_name[r.FileName]
        np.testing.assert_allclose(b.drill, r.drill)
        assert b.DOB == pytest.approx(r.DOB)


@pytest.mark.parametrize('prefix', [
    'victim(a int); DROP TABLE victim; CREATE TABLE IF NOT EXISTS z',
    'x; DROP TABLE victim; --',
    'a b',
    '1abc',
    'a-b',
    'a"b',
])
def test_hostile_prefix_rejected(conn, prefix):
    conn.execute('CREATE TABLE victim (a INTEGER)')
    rs = ResiResultSet(SAMPLE)
    with pytest.raises(ValueError):
        rs.to_duckdb(conn, table_prefix=prefix)
    with pytest.raises(ValueError):
        ResiResultSet.from_duckdb(conn, table_prefix=prefix)
    tables = {t for (t,) in conn.execute('SHOW TABLES').fetchall()}
    assert tables == {'victim'}


def test_table_names():
    assert duckdb_table_names('p_') == ('p_traces', 'p_results', 'p_rings', 'p_boards')
    assert duckdb_table_names() == ('traces', 'results', 'rings', 'boards')


def test_failed_insert_rolls_back(conn, monkeypatch):
    rs = ResiResultSet(SAMPLE)

    def boom(*a, **k):
        raise RuntimeError('insert failed')
    monkeypatch.setattr(ResiResultSet, '_insert_duckdb_rows', staticmethod(boom))
    with pytest.raises(RuntimeError):
        rs.to_duckdb(conn)
    # connection must still be usable, with no half-written rows
    assert conn.execute('SELECT count(*) FROM traces').fetchone()[0] == 0
    monkeypatch.undo()
    rs.to_duckdb(conn)
    assert conn.execute('SELECT count(*) FROM traces').fetchone()[0] == len(rs)
