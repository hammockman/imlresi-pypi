# Changelog

## Unreleased (0.0.46)

### Check data written by 0.0.45 and earlier

- **FeedSpeed units.** `.Resi` files, DuckDB databases and Delta tables
  written by `save_traces_to_dotresi` stored FeedSpeed in cm/min (e.g. 200)
  instead of the mm/min the web app uses (2000). The density
  standardisation assumes mm/min, so recomputed density for those traces is
  off. Multiply FeedSpeed by 10 for rows written from raw traces by this
  library; files written by the web app itself are fine.
- **DOB.** Loading a web-app `.Resi` file replaced DOB with the (usually NA)
  DBHOB column, so anything exported from it (`.Resi`, DuckDB, Delta) has no
  DOB. Re-export from the original `.Resi` files.
- **SampleDate.** Traces saved with `save_traces_to_dotresi` lost their time
  of day (00:00:00), and month-first dates such as `10/27/2020` from web-app
  files could be read day-first.
- **`Trace.hash()`.** Since February 2026, binary and text traces hashed
  differently from earlier releases. This release restores the earlier
  JSON for them; hashes of traces stored since February may differ.

### Fixed

- Delta merge or append through a `DeltaTable`, a `file://` URI or a remote
  URI could overwrite the whole table; so could a failed table lookup on
  Spark. Creating a new table never replaces what is already there.
- `to_duckdb`/`from_duckdb`: `table_prefix` could inject SQL; it must now be a
  plain identifier. A failed insert rolls back. `ResiFile` holds the `.Resi`
  path; missing RPMCoef and RadialPositionPct are no longer invented;
  EqnType and Version are stored; a result is only skipped as a duplicate if
  every processing setting matches.
- `change_instrument_id` left the old ID in ringData.
- `save_traces_to_dotresi(append=True)` duplicated traces already in the
  file; TreeID came from the trace's comment instead of its ID.
- `recompute_*` failed or returned NaN for NA descriptors.
- `Trace.get_bark_thickness()` exit bark included the entry bark.
- `Trace`, `ResiResult` and `ResiResultSet` can be copied and pickled
  (multiprocessing, Spark).
- A mistyped `Trace.get_*()` raises `AttributeError` after processing
  instead of returning None.
- Reading: `.pdc` locations under a non-UTF-8 locale (Windows), PD-Tools
  text exports in cp1252, binary traces with trailing bytes, and
  unsupported files raise `ValueError` instead of failing an `assert`.
- `process_using_resiapi` sends only the trace's file name, and accepts a
  `Path`.

### Added

- Extras: `delta`, `spark`, `plot`.
- `traces2resi` command.
