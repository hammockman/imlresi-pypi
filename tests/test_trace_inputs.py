"""Trace reading edge cases: encodings, damaged files, printing, API input."""
import builtins
import json
from pathlib import Path
from unittest import mock

import pytest

from imlresi import Trace
from imlresi import trace as T

DATA = Path(__file__).parent / 'data'
PDCS = ['2-178-withfeed.pdc', '7-561_COOCHI_203_H_01M103.pdc', '8-LILLIP_20A_H_19903M39.pdc', '9-HARWOO_5_H_4351TM20.pdc']


def read(path):
    t = Trace()
    t.read(path)
    return t


@pytest.mark.parametrize('name', PDCS)
def test_latlon_independent_of_locale(name):
    """On Windows the default encoding is cp1252; .pdc locations contain ° and ±."""
    expected = read(DATA / name).get_latlon()
    real_open = builtins.open

    def cp1252_default(f, mode='r', *a, **k):
        if 'b' not in mode and 'encoding' not in k:
            k['encoding'] = 'cp1252'
        return real_open(f, mode, *a, **k)

    with mock.patch('builtins.open', cp1252_default):
        assert read(DATA / name).get_latlon() == expected


def test_txt_export_in_cp1252(tmp_path):
    lines = (DATA / '1-131-withfeed-txt1.txt').read_text().splitlines()
    lines[123] = 'Stamm Nr. 5 – 3°'  # a comment line with non-ASCII
    p = tmp_path / 'cp1252.txt'
    p.write_bytes('\r\n'.join(lines).encode('cp1252'))
    t = read(p)
    assert t.trace_format == 'txt1'
    assert '3°' in t.get_comment()
    assert t.drill == read(DATA / '1-131-withfeed-txt1.txt').drill


def test_trailing_bytes_are_ignored():
    t = read(DATA / '6-131-nofeed-withtrailingrubbish.rgp')
    assert t.trace_format == 'bin'
    assert len(t.drill) > 0


def test_odd_length_binary(tmp_path):
    p = tmp_path / 'odd.rgp'
    good = (DATA / '1-131-withfeed.rgp').read_bytes()
    p.write_bytes(good + b'\x00')
    assert read(p).drill == read(DATA / '1-131-withfeed.rgp').drill


def test_binary_without_data(tmp_path):
    raw = (DATA / '1-131-withfeed.rgp').read_bytes()
    t = Trace()
    t.read(DATA / '1-131-withfeed.rgp')
    header_len = len(raw) - 2 * (len(t.drill) + len(t.feed))
    p = tmp_path / 'empty.rgp'
    p.write_bytes(raw[:header_len])
    with pytest.raises(ValueError, match='no drill data'):
        Trace().read(p)


def test_unsupported_json_trace(tmp_path):
    J, _ = T.load_iml_json(DATA / '1-131-withfeed-json.rgp')  # raw file has literal tabs
    J['version'] = 3
    p = tmp_path / 'v3.rgp'
    p.write_text(json.dumps(J))
    with pytest.raises(ValueError, match='unsupported trace'):
        Trace().read(p)


def test_str_shows_feed_under_feed_heading():
    t = read(DATA / '1-131-withfeed-json.rgp')
    s = str(t)
    feed_part = s.split('*** FEED FORCE ***')[1]
    assert str(t.feed[:13]) in feed_part
    assert str(t.drill[:13]) not in feed_part


def test_str_without_feed():
    t = read(DATA / '1-131-withfeed-txt1.txt')
    t.feed = None
    assert '*** FEED FORCE ***' in str(t)


@pytest.mark.parametrize('as_path', [True, False])
def test_api_gets_file_name_only(as_path):
    path = (DATA / '2-178-withfeed.pdc').resolve()
    t = Trace()
    t.read(path if as_path else str(path))
    with mock.patch('requests.post') as post:
        post.return_value.status_code = 200
        post.return_value.json.return_value = {'UBDIA': 1.0}
        t.process_using_resiapi('https://api.example.com/predict')
    sent = post.call_args.kwargs['json']
    assert sent['trace_filename'] == '2-178-withfeed.pdc'
    json.dumps(sent)  # must be serialisable


def test_warnings_go_through_standard_logging(caplog):
    # so applications' logging handlers (e.g. HQP's) see them
    import logging
    with caplog.at_level(logging.WARNING, logger='imlresi'):
        assert Trace().get_ubdia() is None
    assert any(r.name == 'imlresi.trace' and 'Processing required' in r.getMessage()
               for r in caplog.records)


CORPUS_TRACES = Path(__file__).parent / 'data' / 'corpus' / 'traces'


@pytest.mark.parametrize('name, tilt', [('T001.rgp', None), ('T033.txt', None),   # no tilt recorded
                                        ('T032.pdc', 90.0), ('T035.rgp', 52.7)])
def test_get_tilt(name, tilt):
    t = Trace()
    t.read(CORPUS_TRACES / name)
    assert t.get_tilt() == tilt


@pytest.mark.parametrize('getter', ['get_bark_thickness', 'get_cambial_boundaries', 'get_wood_only'])
def test_result_getters_before_processing(getter, caplog):
    # like plain results (get_ubdia() etc.): None and a warning, not a TypeError
    import logging
    t = Trace()
    t.read(CORPUS_TRACES / 'T020.rgp')
    with caplog.at_level(logging.WARNING, logger='imlresi'):
        assert getattr(t, getter)() is None
    assert any('Processing required' in r.getMessage() for r in caplog.records)
