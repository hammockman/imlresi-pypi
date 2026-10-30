# imlresi
Tools for dealing with [IML-Resi PowerDrill](https://www.iml-service.com/product/iml-powerdrill/) data using python.

**THIS PACKAGE IS UNOFFICAL AND HAS BEEN DEVELOPED INDEPENDENT OF IML**

Current limitations:

1. Focus is on actual measurements made by the tool rather than meta-info.
1. Poor support for data generated in PD-Tools (e.g. "assessments").


## Install

https://pypi.org/project/imlresi/

```sh
pip install imlresi
```

Optional extras:

| extra | for |
|---|---|
| `imlresi[delta]` | Delta Lake export with the pure-Python delta-rs engine |
| `imlresi[spark]` | Delta Lake export through PySpark (e.g. Microsoft Fabric notebooks) |
| `imlresi[plot]` | `Trace.plot()` |
| `imlresi[test]` | running the test suite |


## Use

### Traces

`Trace` reads a single measurement in any of IML's formats: binary `.rgp`
(firmware up to 1.32), JSON `.rgp` (later firmware), `.pdc` (IML's iPad
app) and the two PD-Tools text exports.

```python
from imlresi import Trace

tr = Trace()
tr.read('trace.rgp')
tr.drill, tr.feed            # drill and feed amplitude profiles
tr.get_drilltime()           # instrument clock time
tr.get_latlon()              # from a .pdc location stamp
tr.to_json()                 # as IML's JSON trace format
tr.hash()                    # md5 of to_json(), e.g. as a database key
```

`Trace.process_using_resiapi(uri)` sends the trace to a Resi API server and
keeps the result, which is then available as e.g. `tr.get_ubdia()`. A server
that wants a login gets it with `auth=(name, key)` (only over `https://`):

```python
tr.process_using_resiapi("https://resiapi.aliente.ch/predict",
                         auth=(os.environ["RESI_API_USER"], os.environ["RESI_API_KEY"]))
```

### .Resi files

A `.Resi` file is the project file of the FWPA web app: an R list saved with
`saveRDS()`, holding a summary table (`df`) plus the traces and results for
each measurement.

```python
from imlresi import ResiResultSet, save_traces_to_dotresi, change_instrument_id

rs = ResiResultSet('project.Resi')
for r in rs:
    r.FileName, r.TreeID, r.DOB, r.drill
    r.recompute_den_trace()  # recompute the density profile

rs.to_dotresi('copy.Resi')

# build a .Resi file from raw traces, e.g. to upload to the web app
save_traces_to_dotresi([tr], 'new.Resi')

change_instrument_id('project.Resi', 'PD500-0755', output_filepath='fixed.Resi')
```

The same conversion from the command line:

```sh
traces2resi *.rgp -o new.Resi
```

### Databases

```python
rs.to_duckdb('resi.duckdb')                      # traces, results, rings, boards tables
rs = ResiResultSet.from_duckdb('resi.duckdb')

rs.to_deltalake('Tables/resi', mode='merge')     # needs imlresi[delta] or imlresi[spark]
```

`to_deltalake` uses PySpark when a Spark session is active and delta-rs
otherwise; pass `engine='deltalake'` or `engine='spark'` to choose, and
`storage_options` imply delta-rs. Merging never replaces an existing table;
only `mode='overwrite'` does.


## Units

FeedSpeed is stored in mm/min in `.Resi` files, DuckDB and Delta tables, as
the web app does. Traces report it in cm/min (`Trace.get_feedspeed()`). See
[CHANGELOG.md](CHANGELOG.md) about data written by 0.0.45 and earlier.


## Development

```sh
pip install -e '.[test,spark]'
pytest
```

The Spark tests need a JDK and are skipped without PySpark.
