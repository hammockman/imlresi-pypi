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


def test_resi_file_is_source_path(conn):
    rs = ResiResultSet(SAMPLE)
    rs.to_duckdb(conn)
    files = {f for (f,) in conn.execute('SELECT DISTINCT ResiFile FROM results').fetchall()}
    assert files == {str(SAMPLE)}
    back = ResiResultSet.from_duckdb(conn)
    assert {r.ResiFile for r in back} == {str(SAMPLE)}


def test_missing_values_not_invented(conn):
    rs = ResiResultSet(SAMPLE)
    for r in rs:
        r.descriptors.pop('RPMCoef', None)
        for b in r.board_moe:
            b.pop('RadialPositionPct', None)
    rs.to_duckdb(conn)
    assert conn.execute('SELECT count(*) FROM results WHERE RPMCoef IS NOT NULL').fetchone()[0] == 0
    assert conn.execute('SELECT count(*) FROM boards WHERE RadialPositionPct IS NOT NULL').fetchone()[0] == 0


def test_eqn_type_and_version_stored(conn):
    rs = ResiResultSet(SAMPLE)
    for r in rs:
        r.descriptors['EqnType'] = 'Ln'
        r.descriptors['Version'] = 'Version 5.6.0'
    rs.to_duckdb(conn)
    back = ResiResultSet.from_duckdb(conn)
    assert {(r.EqnType, r.Version) for r in back} == {('Ln', 'Version 5.6.0')}


def test_old_schema_gets_new_columns(conn):
    """A database written before EqnType/Version existed is upgraded in place."""
    rs = ResiResultSet(SAMPLE)
    rs.to_duckdb(conn)
    conn.execute('ALTER TABLE results DROP COLUMN EqnType')
    conn.execute('ALTER TABLE results DROP COLUMN Version')
    rs2 = ResiResultSet(SAMPLE)
    for r in rs2:
        r.descriptors['EqnType'] = 'Ln'
    rs2.to_duckdb(conn)
    cols = {c for (c,) in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='results'").fetchall()}
    assert {'EqnType', 'Version'} <= cols


@pytest.mark.parametrize('field, value', [
    ('EqnType', 'Ln'), ('Resource', 'HoopPine'), ('BLCorrDen', 123.0), ('Standardised', False),
    ('RPMCoef', -0.5), ('TreeClass', 'Other'), ('Version', 'Version 5.6.0'),
])
def test_changed_processing_is_not_a_duplicate(conn, field, value):
    ResiResultSet(SAMPLE).to_duckdb(conn)
    n0 = conn.execute('SELECT count(*) FROM results').fetchone()[0]
    rs = ResiResultSet(SAMPLE)
    for r in rs:
        r.descriptors[field] = value
    rs.to_duckdb(conn)
    assert conn.execute('SELECT count(*) FROM results').fetchone()[0] == 2 * n0
    assert conn.execute('SELECT count(*) FROM traces').fetchone()[0] == n0


def test_identical_rerun_is_skipped(conn):
    ResiResultSet(SAMPLE).to_duckdb(conn)
    n0 = conn.execute('SELECT count(*) FROM results').fetchone()[0]
    with pytest.warns(UserWarning, match='Skipped duplicate'):
        ResiResultSet(SAMPLE).to_duckdb(conn)
    assert conn.execute('SELECT count(*) FROM results').fetchone()[0] == n0


def test_duplicate_within_one_batch(conn):
    rs = ResiResultSet(SAMPLE)
    rs.to_duckdb(conn)
    n0 = conn.execute('SELECT count(*) FROM results').fetchone()[0]
    twice = ResiResultSet(SAMPLE)
    extra = ResiResultSet(SAMPLE)
    for r in list(twice) + list(extra):
        r.descriptors['EqnType'] = 'Ln'
    twice.results += extra.results
    with pytest.warns(UserWarning, match='Skipped duplicate'):
        twice.to_duckdb(conn)
    assert conn.execute('SELECT count(*) FROM results').fetchone()[0] == 2 * n0
