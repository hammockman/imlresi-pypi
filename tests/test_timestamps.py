"""SampleDate parsing, using the shapes FQResi actually writes."""
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
import rdata

from imlresi import ResiResultSet, Trace, save_traces_to_dotresi
from imlresi.dotresi import clean_timestamp, slashed_date_order

DATA = Path(__file__).parent / 'data'


@pytest.mark.parametrize('raw, expected', [
    ('2026-06-07 09:13:54', datetime(2026, 6, 7, 9, 13, 54)),
    ('2019-03-18 11:52', datetime(2019, 3, 18, 11, 52)),
    ('10/27/2020 11:06:14', datetime(2020, 10, 27, 11, 6, 14)),   # FQResi, JSON traces: month first
    ('02/03/2021 08:23', datetime(2021, 2, 3, 8, 23)),
    ('18:41:40 28.07.2015', datetime(2015, 7, 28, 18, 41, 40)),   # time first, dotted date
    ('28.07.2015 18:41:40', datetime(2015, 7, 28, 18, 41, 40)),
    ('2019-04-10 2019-04-10', datetime(2019, 4, 10)),             # date written twice
    ('2022-04-03T10:00:00+10:00', datetime(2022, 4, 3, 10, 0)),   # ISO is never day-first
    ('2022-04-03', datetime(2022, 4, 3)),
    (['2026-06-07 09:13:54'], datetime(2026, 6, 7, 9, 13, 54)),
    (pd.Timestamp('2022-04-03 10:00', tz='Australia/Brisbane'), datetime(2022, 4, 3, 10, 0)),
])
def test_clean_timestamp(raw, expected):
    got = clean_timestamp(raw)
    assert got == expected
    assert got.tzinfo is None


@pytest.mark.parametrize('raw', [None, '', 'NA', '<NA>', 'Not Available', '?', float('nan'), pd.NA, [], '13/13/2020 10:00'])
def test_clean_timestamp_missing(raw):
    assert clean_timestamp(raw) is None


def test_day_first_order():
    assert clean_timestamp('02/03/2021 08:23', 'DMY') == datetime(2021, 3, 2, 8, 23)


@pytest.mark.parametrize('values, order', [
    (['10/27/2020 11:06:14', '02/03/2021 08:23'], 'MDY'),
    (['02/03/2021 08:23', '28/07/2015 18:41:40'], 'DMY'),  # binary .rgp via FQResi: dd/mm
    (['02/03/2021 08:23'], 'MDY'),
    (['2026-06-07 09:13:54'], 'MDY'),
    ([], 'MDY'),
])
def test_slashed_date_order(values, order):
    assert slashed_date_order(values) == order


@pytest.mark.parametrize('path', sorted(DATA.glob('*.Resi')), ids=lambda p: p.name)
def test_sample_dates_match_raw(path):
    df = rdata.conversion.convert(rdata.parser.parse_file(str(path)))['df']
    rs = ResiResultSet(path)
    for r, raw in zip(rs, df['SampleDate']):
        assert r.SampleDate == clean_timestamp(raw)
        assert r.SampleDate is not None


def test_save_traces_keeps_time(tmp_path):
    tr = Trace()
    tr.read(DATA / '2-178-withfeed.pdc')
    out = tmp_path / 'one.Resi'
    save_traces_to_dotresi([tr], out)
    df = rdata.conversion.convert(rdata.parser.parse_file(str(out)))['df']
    assert df['SampleDate'][0] == tr.get_drilltime().strftime('%Y-%m-%d %H:%M:%S')
    assert not df['SampleDate'][0].endswith('00:00:00')
    assert ResiResultSet(out)[0].SampleDate == tr.get_drilltime()
