# Changelog

## Unreleased

### Added

- `Trace.process_using_resiapi()` and `ResiResultSet.load_traces()` take
  `auth`, the API server's login (a `(name, key)` pair or any requests
  auth), sent only to an `https://` server.

### Fixed

- `imlresi[delta]` installed pyarrow 26, which needs numpy 2, alongside
  imlresi's numpy 1 and failed on import; the extra now caps `pyarrow <26`.
- `recompute_den_trace()` with the NonLinear baseline used FQResi's current
  correction for every app version. Files from app 5.0–5.4 (and
  4.5.4–4.5.x) were made with the earlier void-volume correction; the
  library now follows the app version, and matches app 5.0.0 densities
  exactly (it was ~1.2% off). Eglobulus used the wrong sigmoid offset
  (6 instead of 7.5).
- Density recomputation used RPM coefficients a=-0.8, b=1 when a file
  doesn't store them (4.2.4 files never do); FQResi uses -0.786, 1 for
  every instrument but one. Traces measured at other than 2500 rpm were
  ~0.3% off; they are now exact.
- Density recomputation for app 5.0–5.4 files used the standardisation
  FQResi adopted for app 5.5 (it matters at other than 2000 mm/min and
  2500 rpm); those files now use the earlier formulas. An unknown Resource
  is no longer standardised as RadiataPine (FQResi leaves it as is from
  5.5). The Ln equation's mean now covers exactly FQResi's samples. Checked
  against FQResi's own R code (`tools/fqresi_reference.py`).
- `to_dotresi` and `save_traces_to_dotresi` filled in missing `denTraces`
  and `cumDenTraces` with the library's own recomputation, which then read
  back as the app's. For raw traces saved without API results, the inputs
  were placeholders (diameter = trace length, no baseline correction,
  slope 1), so those densities were meaningless. Only densities from the
  app or the API are written now; recompute them with
  `recompute_den_trace()`. Density stored as text by the app is written
  back as numbers.
- Paths: relative `Files/...` and `Tables/...` paths were always taken to
  mean the Fabric lakehouse (`/lakehouse/default/...`), even outside Fabric;
  now only when the mount exists and no such local path does. `abfss://`
  URIs that aren't OneLake were silently rewritten to a wrong lakehouse path;
  they now raise `ValueError`. `to_dotresi` resolves paths the same way as
  reading does, so `Files/x.Resi` names the same file in both.
- `to_deltalake` used Spark whenever a session was active, even when
  given `storage_options` (which Spark ignores) or when delta-rs was
  wanted; the new `engine` argument chooses, and `storage_options` imply
  delta-rs. A schema-merging Spark merge set
  `spark.databricks.delta.schema.autoMerge.enabled` for the rest of the
  session; it now uses the merge's own schema evolution.
- Reading a `.Resi` file had no size limits, so a file of a few hundred
  bytes could make it allocate gigabytes, either as a compression bomb or
  as a compact R sequence (`1:2e9`, stored as just its ends). Data beyond
  `imlresi.dotresi.MAX_RESI_BYTES` (1 GiB once decompressed; real files
  reach ~160 MB) now raises `ValueError`.
- `Trace.get_tilt()` raised `KeyError` for binary `.rgp` and PD-Tools text
  traces, which record no tilt; it returns None, as it already did when
  tilt was off. `get_bark_thickness()`, `get_cambial_boundaries()` and
  `get_wood_only()` failed with `TypeError`/`AttributeError` before API
  processing; like the other result getters, they now warn and return None.

### Changed

- Logging goes through the standard `logging` module (loggers
  `imlresi.trace`, `imlresi.dotresi`) instead of loguru, so applications'
  logging configuration applies; loguru is no longer a dependency.
  Unconfigured, warnings still reach stderr.

## 0.0.46 (2026-10-30)

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
- **`Trace.hash()` of binary and text traces changes.** `to_json()` of a
  binary `.rgp` or PD-Tools text trace wrote `depthMsmt` and `deviceLength`
  in mm where IML's JSON uses cm (154.3 instead of 15.43); they are now in
  cm. Settings these formats lack (`depthPresel`, `feedOn`, ...) are written
  as 0 again, as before February 2026, instead of null. Both change the JSON,
  and so `Trace.hash()`, of every binary and text trace. JSON `.rgp` and
  `.pdc` traces are unaffected. Nothing in FQResi or the Resi API reads the
  two depth fields, so no results were affected by the wrong values.
- **Anything hashing the API request** (e.g. an `md5` of `trace._inp`)
  changes for every trace: besides the above, `process_using_resiapi` now
  sends only the trace's file name, not its full local path.

### Fixed

- `.Resi` writing used invented column layouts: the "4.8.0" one lacked
  DOB, Version, EqnType, MOEmodel, RadialMOEMethod, CheckStatus and
  AdjustRecord (losing EqnType turns an "Ln" calibration into "Linear"),
  and the "4.2.4" one added columns real 4.2.4 files don't have. Layouts
  are now taken from real web-app files ('4.2.4', '4.5.1', '5.6.0'; '4.8.0'
  is an alias of '5.6.0'). A file loaded and written back keeps its own
  layout and every unchanged value exactly; `to_dotresi` and
  `change_instrument_id` no longer convert files unless asked to.
- A trace with no feed data (R `list(NULL)`) loaded as a one-sample NaN
  feed trace.
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
