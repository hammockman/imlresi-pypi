"""Trace.hash() is used as a database key, so it must not change by accident.

If a change to parsing or to_json() alters these values on purpose,
existing databases keyed on the old hash need migrating: update the pins
only alongside that.
"""
from pathlib import Path

import pytest

from imlresi import Trace

DATA = Path(__file__).parent / 'data'

PINNED = {
    '1-131-withfeed-json.rgp': '6b46a40e7b8cee4dc1ebb18516241ca4',
    '1-131-withfeed-pdtools122.rgp': '288bc46edf7e80d1457cd7247adc871c',
    '1-131-withfeed-pdtools167.rgp': '6b46a40e7b8cee4dc1ebb18516241ca4',
    '1-131-withfeed-txt1.txt': 'e64dd37d39977354aec269485fd865b5',
    '1-131-withfeed-txt2.txt': 'e64dd37d39977354aec269485fd865b5',
    '1-131-withfeed.rgp': '288bc46edf7e80d1457cd7247adc871c',
    '2-178-withfeed.pdc': 'a07a37875ff4d4a8881b98d386a33be8',
    '3-131-nofeed.rgp': 'cbcc7eb33348d3a20ba89ac8e225b7aa',
    '4-131-withfeed.rgp': '05bb8ab37b20088a16236c646aa84971',
    '5-132-withfeed.rgp': '54580635903dd20e0cb08eeef3381ad6',
    '7-561_COOCHI_203_H_01M103.pdc': 'a05a9e7d6c3e3502d95412937de889aa',
    '8-LILLIP_20A_H_19903M39.pdc': '12e1aaad620dabe2fed96c9b49e59611',
    '9-HARWOO_5_H_4351TM20.pdc': '8bfeb0db7e2908a9cf7f02f5707a9a79',
}


@pytest.mark.parametrize('name', PINNED)
def test_hash_pinned(name):
    tr = Trace()
    tr.read(DATA / name)
    assert tr.hash() == PINNED[name]


def test_hash_ignores_read_path():
    a, b = Trace(), Trace()
    a.read(DATA / '1-131-withfeed.rgp')
    b.read(str((DATA / '1-131-withfeed.rgp').resolve()))
    assert a.hash() == b.hash()


@pytest.mark.parametrize('name', ['1-131-withfeed.rgp', '1-131-withfeed-txt1.txt', '1-131-withfeed-txt2.txt'])
def test_converted_trace_keeps_template_defaults(name):
    """Settings older formats lack are written as the template's 0, not None
    (the stored fq156 JSON for pre-1.32 traces has 0 here)."""
    tr = Trace()
    tr.read(DATA / name)
    h = tr.to_dict()['header']
    for k in ('feedOn', 'ncOn', 'ncState', 'tiltOn', 'tiltRelOn', 'tiltRelAngle', 'tiltAngle'):
        if k not in tr.settings:
            assert h[k] == 0, k
