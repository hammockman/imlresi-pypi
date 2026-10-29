import tempfile
import warnings
from pathlib import Path
import pytest
import numpy as np
import duckdb
from imlresi import ResiResult, ResiResultSet

def test_load_resi_calitris():
    """
    Verifies parsing, loading, and mathematical recomputations of Calitris Resi file.
    """
    filepath = Path('/home/jh/tmp/dotResi/Calitris_pith_and_bark_adjusted.Resi')
    if not filepath.exists():
        pytest.skip("Test Resi file not found")

    # Catch warnings during validation checks
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        rs = ResiResultSet(filepath)
        print(f"Warnings caught on load: {[str(item.message) for item in w]}")

    assert len(rs) > 0
    print(f"Loaded {len(rs)} records from Calitris Resi file.")

    first_res = rs[0]
    assert first_res.FileName is not None
    assert first_res.TreeID is not None

    # Verify legacy DOB mapping (DBHOB -> DOB)
    assert first_res.DOB is not None

    # Check trace signals are arrays
    assert first_res.drill is not None
    assert isinstance(first_res.drill, np.ndarray)
    assert first_res.feed is not None
    assert isinstance(first_res.feed, np.ndarray)

    # Verify trace hash exists
    assert first_res.TraceHash is not None
    assert len(first_res.TraceHash) == 64  # SHA-256 length

    # Test trace recomputations
    corr = first_res.recompute_corr_trace()
    assert corr is not None
    assert len(corr) <= len(first_res.drill)

    den = first_res.recompute_den_trace()
    assert den is not None

    cum_den = first_res.recompute_cum_den_trace()
    assert cum_den is not None

def test_load_resi_fq2():
    """
    Verifies parsing of trace files with missing variables (e.g. no feed).
    """
    filepath = Path('/home/jh/tmp/dotResi/FQ2 ResiRPM Comparison_03Jul2020.Resi')
    if not filepath.exists():
        pytest.skip("Test Resi file not found")

    rs = ResiResultSet(filepath)
    assert len(rs) > 0
    print(f"Loaded {len(rs)} records from FQ2 Resi file.")

    # FQ2 has no feed trace, must gracefully set feed to None
    first_res = rs[0]
    assert first_res.feed is None
    assert first_res.drill is not None

def test_duckdb_roundtrip():
    """
    Tests DuckDB schema creation, database insertion, append, duplicate check, and ORM reconstruction.
    """
    filepath = Path('/home/jh/tmp/dotResi/Calitris_pith_and_bark_adjusted.Resi')
    if not filepath.exists():
        pytest.skip("Test Resi file not found")

    rs = ResiResultSet(filepath)

    # Setup temporary duckdb database file
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        # Write dataset to DuckDB
        rs.to_duckdb(db_path)

        # Verify writing created all correct tables
        conn = duckdb.connect(str(db_path))
        tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
        assert "traces" in tables
        assert "results" in tables
        assert "rings" in tables
        assert "boards" in tables

        # Verify row count matches
        traces_count = conn.execute("SELECT count(*) FROM traces").fetchone()[0]
        results_count = conn.execute("SELECT count(*) FROM results").fetchone()[0]
        assert traces_count == len(rs)
        assert results_count == len(rs)

        # Try inserting again (should warn and skip identical duplicates)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rs.to_duckdb(conn)
            # Ensure skip warning was issued
            assert len(w) > 0
            assert "Skipped duplicate insert" in str(w[0].message)

        # Test loading from DuckDB
        loaded_rs = ResiResultSet.from_duckdb(conn)
        assert len(loaded_rs) == len(rs)

        # Check first record contents matches
        assert loaded_rs[0].FileName == rs[0].FileName
        assert len(loaded_rs[0].drill) == len(rs[0].drill)

        # Test custom sql query load (load only CALITRISM001.rgp)
        query_sql = "SELECT r.* FROM results r JOIN traces t ON r.TraceID = t.id WHERE t.FileName = 'CALITRISM001.rgp'"
        single_rs = ResiResultSet.from_duckdb(conn, sql_query=query_sql)
        assert len(single_rs) == 1
        assert single_rs[0].FileName == 'CALITRISM001.rgp'

        conn.close()

def test_save_traces_to_resi():
    """
    Tests saving trace objects to .Resi files, as well as appending and duplicate check.
    """
    import tempfile
    from imlresi import Trace, save_traces_to_dotresi

    # Create mock Trace objects
    t1 = Trace()
    t1.trace_filename = "mock_trace_1.rgp"
    t1.header = {
        'tree_id': 'Tree-A',
        'toolserial': 'PD500-1023',
        'dateTime': '2026-07-08 12:00:00'
    }
    t1.settings = {
        'feed_speed': 400.0,
        'needle_speed': 2200.0
    }
    t1.drill = [10.0, 20.0, 30.0, 15.0]
    t1.feed = [5.0, 6.0, 5.5, 4.0]

    t2 = Trace()
    t2.trace_filename = "mock_trace_2.rgp"
    t2.header = {
        'tree_id': 'Tree-B',
        'toolserial': 'PD500-test',
        'dateTime': '2026-07-08 13:00:00'
    }
    t2.settings = {
        'feed_speed': 500.0,
        'needle_speed': 2500.0
    }
    t2.drill = [12.0, 22.0, 32.0, 17.0]
    t2.feed = [6.0, 7.0, 6.5, 5.0]

    with tempfile.TemporaryDirectory() as tmpdir:
        resi_path = Path(tmpdir) / "test_write.Resi"

        # Save first trace
        save_traces_to_dotresi(t1, resi_path)
        assert resi_path.exists()

        # Load and verify
        rs = ResiResultSet(resi_path)
        assert len(rs) == 1
        assert rs[0].FileName == "mock_trace_1.rgp"
        assert rs[0].TreeID == "Tree-A"
        assert rs[0].ResiCode == "PD500-1023"
        assert float(rs[0].FeedSpeed) == 4000.0  # the trace's 400 cm/min, in mm/min
        assert float(rs[0].RPM) == 2200.0
        assert np.array_equal(rs[0].drill, np.array([10.0, 20.0, 30.0, 15.0]))

        # Append second trace
        save_traces_to_dotresi(t2, resi_path)

        rs2 = ResiResultSet(resi_path)
        assert len(rs2) == 2
        assert rs2[1].FileName == "mock_trace_2.rgp"
        assert rs2[1].TreeID == "Tree-B"
        assert rs2[1].ResiCode == "PD500-test"

def test_main_driver_cli():
    """
    Tests the command line interface main driver function inside dotresi module.
    """
    import tempfile
    from imlresi.dotresi import main

    rgp_path = Path("/home/jh/Downloads/879CTBS--004-2-1M121.rgp")
    if not rgp_path.exists():
        pytest.skip("Test rgp file not found")

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "cli_combined.Resi"

        # Invoke main with arguments
        main([str(rgp_path), "-o", str(out_path)])
        assert out_path.exists()

        # Load and verify it parses correctly
        rs = ResiResultSet(out_path)
        assert len(rs) == 1
        assert rs[0].FileName == "879CTBS--004-2-1M121.rgp"

def test_load_traces():
    from unittest.mock import patch
    from imlresi import Trace
    from imlresi.dotresi import ResiResultSet

    tr = Trace()
    tr.trace_filename = "mock_trace_api.rgp"
    tr.trace_format = "rgp"
    tr.drill = [10.0, 20.0, 30.0]
    tr.feed = [5.0, 5.0, 5.0]

    with patch('requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "FileName": "mock_trace_api.rgp",
            "TreeID": "Tree-1",
            "ResiCode": "PD400-0081",
            "SampleDate": "2026-07-08 12:00:00",
            "FeedSpeed": 400.0,
            "RPM": 2200.0,
            "Standardised": True,
            "TraceType": "B-B",
            "BaselineMethod": "Linear",
            "RingMethod": "Annual",
            "DBHOB": 300.0,
            "UBDIA": 300.0,
            "BarkThickness": 0.0,
            "EntryRadius": 150.0,
            "ExitRadius": 300.0,
            "ExitBarkThickness": 0.0,
            "BLCorrDen": 0.0,
            "rSlope": 1.0,
            "rIntcpt": 0.0,
            "drill": [10.0, 20.0, 30.0],
            "feed": [5.0, 5.0, 5.0],
            "rPos": [0.0, 0.1, 0.2],
            "ringData": {
                "RingFromPith": [1.0, 2.0],
                "RingWidth": [2.5, 3.1]
            },
            "rsawmill": {
                "boardMOE": "Small",
                "boardSummary": {
                    "FileName": ["mock_trace_api.rgp"],
                    "TreeID": ["Tree-1"],
                    "AvBoardMOE": [12.5],
                    "DiscMOE": [18.2]
                }
            }
        }

        rs = ResiResultSet()
        rs.load_traces(tr, api_uri="https://api.example.com/resi")

        assert len(rs) == 1
        res = rs[0]
        assert res.FileName == "mock_trace_api.rgp"
        assert res.TreeID == "Tree-1"
        assert res.ResiCode == "PD400-0081"
        assert res.rs_row.get("AvBoardMOE") == 12.5
        assert len(res.ring_data) == 2
        assert res.ring_data[0].get("RingWidth") == 2.5

def test_to_dotresi():
    import tempfile
    import numpy as np
    from imlresi.dotresi import ResiResultSet, ResiResult

    rs = ResiResultSet()

    res = ResiResult(
        filename="test_direct_save.rgp",
        descriptors={
            "FileName": "test_direct_save.rgp",
            "TreeID": "Direct-Tree",
            "ResiCode": "PD400-0081",
            "SampleDate": "2026-07-08 12:00:00",
            "FeedSpeed": 400.0,
            "RPM": 2200.0,
            "Standardised": True,
            "TraceType": "B-B",
            "BaselineMethod": "Linear",
            "RingMethod": "Annual",
            "DBHOB": 1500.0,
            "UBDIA": 1500.0,
            "BarkThickness": 0.0,
            "EntryRadius": 750.0,
            "ExitRadius": 1500.0,
            "ExitBarkThickness": 0.0,
            "BLCorrDen": 0.0,
            "rSlope": 1.0,
            "rIntcpt": 0.0
        },
        drill=np.array([1.0, 2.0, 3.0]),
        feed=np.array([4.0, 5.0, 6.0]),
        rpos=np.array([0.0, 0.1, 0.2]),
        ring_data=[{"RingWidth": 1.5}],
        board_moe=[{"BoardMOE": 12.0}],
        rs_row={"AvBoardMOE": 12.0}
    )
    rs.results.append(res)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "direct.Resi"
        rs.to_dotresi(out_path)
        assert out_path.exists()

        # Load back
        rs2 = ResiResultSet(out_path)
        assert len(rs2) == 1
        assert rs2[0].FileName == "test_direct_save.rgp"
        assert rs2[0].TreeID == "Direct-Tree"
        assert len(rs2[0].ring_data) == 1
        assert rs2[0].ring_data[0].get("RingWidth") == 1.5
        assert len(rs2[0].board_moe) == 1
        assert rs2[0].board_moe[0].get("BoardMOE") == 12.0
        assert rs2[0].rs_row.get("AvBoardMOE") == 12.0


def test_to_deltalake():
    import tempfile
    from deltalake import DeltaTable
    from imlresi.dotresi import ResiResultSet, ResiResult

    rs1 = ResiResultSet()
    rs1.results.append(
        ResiResult(
            filename="trace1.rgp",
            descriptors={"FileName": "trace1.rgp", "TreeID": "Tree-1", "DBHOB": 30.0}
        )
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        delta_path = Path(tmpdir) / "delta_table"

        # Test initial merge/creation
        res1 = rs1.to_deltalake(delta_path, mode="merge", merge_key="FileName")
        assert delta_path.exists()
        assert res1.num_inserted == 1
        assert res1.num_updated == 0
        assert res1[0] == 1  # tuple indexing

        dt1 = DeltaTable(str(delta_path))
        df1 = dt1.to_pandas()
        assert df1.shape[0] == 1
        assert df1.iloc[0]["FileName"] == "trace1.rgp"

        # Test merge update (upsert) trace1 + insert trace2
        rs2 = ResiResultSet()
        rs2.results.append(
            ResiResult(
                filename="trace1.rgp",
                descriptors={"FileName": "trace1.rgp", "TreeID": "Tree-1-Updated", "DBHOB": 35.0}
            )
        )
        rs2.results.append(
            ResiResult(
                filename="trace2.rgp",
                descriptors={"FileName": "trace2.rgp", "TreeID": "Tree-2", "DBHOB": 25.0}
            )
        )

        res2 = rs2.to_deltalake(delta_path, mode="merge", merge_key="FileName")
        assert res2.num_inserted == 1
        assert res2.num_updated == 1
        assert res2[1] == 1  # tuple indexing

        dt2 = DeltaTable(str(delta_path))
        df2 = dt2.to_pandas()
        assert df2.shape[0] == 2
        t1_row = df2[df2["FileName"] == "trace1.rgp"].iloc[0]
        assert t1_row["TreeID"] == "Tree-1-Updated"
        assert t1_row["DBHOB"] == 35.0


def test_save_traces_to_dotresi_creates_output_dir():
    from imlresi.dotresi import save_traces_to_dotresi
    from imlresi.trace import Trace

    tr = Trace()
    tr.read('tests/data/2-178-withfeed.pdc')

    with tempfile.TemporaryDirectory() as tmpdir:
        nested_path = Path(tmpdir) / "nested" / "subfolder" / "output.Resi"
        assert not nested_path.parent.exists()

        save_traces_to_dotresi([tr], nested_path)

        assert nested_path.parent.exists()
        assert nested_path.exists()


def test_normalize_filepath():
    from pathlib import Path
    from imlresi.dotresi import normalize_filepath

    assert normalize_filepath("file:///lakehouse/default/Files/test.Resi") == Path("/lakehouse/default/Files/test.Resi")
    assert normalize_filepath("file:/lakehouse/default/Files/test.Resi") == Path("/lakehouse/default/Files/test.Resi")
    assert normalize_filepath("abfss://workspace@onelake.dfs.fabric.microsoft.com/lakehouse/Files/test.Resi") == Path("/lakehouse/default/Files/test.Resi")
    assert normalize_filepath("abfss://workspace@onelake.dfs.fabric.microsoft.com/lakehouse/Files/sub/test.Resi") == Path("/lakehouse/default/Files/sub/test.Resi")
    assert normalize_filepath("abfss:/Files/test.Resi") == Path("/lakehouse/default/Files/test.Resi")
    assert normalize_filepath("Files/test.Resi") == Path("/lakehouse/default/Files/test.Resi")
    assert normalize_filepath("Tables/my_table") == Path("/lakehouse/default/Tables/my_table")
    assert normalize_filepath("/tmp/test.Resi") == Path("/tmp/test.Resi")


def test_change_instrument_id():
    import tempfile
    from imlresi.dotresi import ResiResultSet, change_instrument_id

    # Load 1_FWPA_4.8.0.Resi
    sample_file = "tests/data/1_HQPAPI_4.2.4.Resi"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "mod.Resi"

        # Change instrument ID
        rs_mod = change_instrument_id(sample_file, "PD500-0999", output_filepath=out_file)

        assert len(rs_mod.results) > 0
        for r in rs_mod.results:
            assert r.ResiCode == "PD500-0999"

        # Load saved file to verify persistence
        rs_loaded = ResiResultSet(out_file)
        assert len(rs_loaded.results) > 0
        for r in rs_loaded.results:
            assert r.ResiCode == "PD500-0999"


def test_to_dotresi_legacy_format():
    import tempfile, rdata
    from imlresi.dotresi import ResiResultSet, LEGACY_DF_COLUMNS

    sample_file = "tests/data/1_HQPAPI_4.2.4.Resi"
    rs = ResiResultSet(sample_file)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_legacy = Path(tmpdir) / "legacy.Resi"

        # Export using legacy format_version="4.2.4"
        rs.to_dotresi(out_legacy, format_version="4.2.4")
        assert out_legacy.exists()

        # Parse raw R objects with rdata to verify structure
        parsed = rdata.parser.parse_file(str(out_legacy))
        converted = rdata.conversion.convert(parsed)

        # 1. regVar should be absent in legacy format
        assert "regVar" not in converted

        # 2. version string check
        version_obj = converted.get("version")
        assert version_obj is not None
        assert "4.2.4" in str(version_obj)

        # 3. df schema column count check (legacy 39 columns vs modern 43)
        df = converted.get("df")
        assert df is not None
        assert df.shape[1] == len(LEGACY_DF_COLUMNS)
        assert "DBHOB" in df.columns
        assert "TreeClass" in df.columns
        assert "RPMCoef" in df.columns
        assert "DOB" not in df.columns


def test_to_dotresi_computed_results_export(tmp_path):
    """Test exporting computed metrics, denTraces, delimiters, and ringData/boardMOE to .Resi files."""
    import rdata
    from imlresi.dotresi import ResiResultSet, ResiResult

    rs = ResiResultSet()
    r = ResiResult(
        filename="computed_test.rgp",
        descriptors={
            "DOB": 150.5,
            "BarkThickness": 12.5,
            "ExitBarkThickness": 10.0,
            "UBDIA": 128.0,
            "EntryRadius": 75.0,
            "ExitRadius": 75.0,
            "TraceType": "B-B",
            "PrAWV": 2850.0,
            "PrMOE": 9.2,
            "OWDensity": 450.0,
            "CoreDensity": 380.0,
            "DiscDensity": 420.0,
            "Decay": 0.0,
            "RingCount": 25.0,
            "BLCorrDen": 5.0,
            "rSlope": 1.2,
            "rIntcpt": 15.0,
            "rPos": np.array([12.5, 75.0, 75.0, 138.0, 150.5])
        },
        drill=np.linspace(10, 50, 1000),
        feed=np.linspace(5, 20, 1000),
        ring_data=[{
            "RingPosition": 10.0,
            "RingWidth": 4.5,
            "RingDensityMean": 460.0,
            "RingMOEMean": 9.8
        }],
        board_moe=[{
            "BoardIndex": 1,
            "MeanMOE": 8.5,
            "BoardMOE": 8.5
        }]
    )
    r.den_trace = np.linspace(350, 480, 1000)
    r.cum_den_trace = np.linspace(350, 450, 1000)
    rs.results.append(r)

    out_file = tmp_path / "computed_export.Resi"
    rs.to_dotresi(out_file, overwrite=True)
    assert out_file.exists()

    # Parse raw R objects with rdata to verify structure
    parsed = rdata.parser.parse_file(str(out_file))
    converted = rdata.conversion.convert(parsed)

    # Verify denTraces and cumDenTraces are present and not None
    den_traces = converted.get("denTraces")
    cum_den_traces = converted.get("cumDenTraces")
    assert den_traces is not None
    assert cum_den_traces is not None
    assert "computed_test.rgp" in den_traces
    assert "computed_test.rgp" in cum_den_traces
    assert len(den_traces["computed_test.rgp"]) == 1000

    # Verify df table contains computed summary metrics and bark/wood delimiters
    df = converted.get("df")
    assert df is not None
    row = df.iloc[0]
    assert row["DBHOB"] == 150.5
    assert row["BarkThickness"] == 12.5
    assert row["UBDIA"] == 128.0
    assert row["PrAWV"] == 2850.0
    assert row["PrMOE"] == 9.2
    assert row["OWDensity"] == 450.0

    # Verify ringData and boardMOE
    ring_data = converted.get("ringData")
    assert ring_data is not None
    assert len(ring_data) == 1
    assert ring_data.iloc[0]["RingDensityMean"] == 460.0

    board_moe = converted.get("boardMOE")
    assert board_moe is not None
    assert len(board_moe) == 1
    assert board_moe.iloc[0]["MeanMOE"] == 8.5

