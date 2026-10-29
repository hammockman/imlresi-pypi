"""Trace.hash() is used as a database key, so it must not change by accident.

If a change to parsing or to_json() alters these values on purpose,
existing databases keyed on the old hash need migrating: update the pins
only alongside that.
"""
from pathlib import Path

import pytest

from imlresi import Trace

DATA = Path(__file__).parent / 'data'

# Pins for converted (binary and txt) traces changed in 0.0.46: depthPresel
# went back to the template's 0 (as before Feb 2026) instead of null, and
# depthMsmt/deviceLength are now in cm like IML's own JSON instead of mm.
PINNED = {
    '1-131-withfeed-json.rgp': '6b46a40e7b8cee4dc1ebb18516241ca4',
    '1-131-withfeed-pdtools122.rgp': 'a6b1bb71ba4fb9bb54e117eabcffa579',
    '1-131-withfeed-pdtools167.rgp': '6b46a40e7b8cee4dc1ebb18516241ca4',
    '1-131-withfeed-txt1.txt': '5316f98b1ab8850e535b046d4c2c1f06',
    '1-131-withfeed-txt2.txt': '5316f98b1ab8850e535b046d4c2c1f06',
    '1-131-withfeed.rgp': 'a6b1bb71ba4fb9bb54e117eabcffa579',
    '2-178-withfeed.pdc': 'a07a37875ff4d4a8881b98d386a33be8',
    '3-131-nofeed.rgp': '69ee6364f5ce6488aeb8b3e037e35ac4',
    '4-131-withfeed.rgp': '6bbd64e3a9cc67eab97ef86760e8ad8d',
    '5-132-withfeed.rgp': 'babaf155cb74d585a1c7b2d38785abda',
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


SAME_MEASUREMENT = ['1-131-withfeed-json.rgp', '1-131-withfeed.rgp', '1-131-withfeed-txt1.txt', '1-131-withfeed-txt2.txt']


def test_depths_in_cm_for_every_format():
    """One measurement in four formats: to_json() reports the same depths, in
    cm as IML's JSON does (1543 points at 0.1 mm = 15.43 cm)."""
    for name in SAME_MEASUREMENT:
        tr = Trace()
        tr.read(DATA / name)
        h = tr.to_dict()['header']
        assert h['depthMsmt'] == pytest.approx(15.43), name
        assert h['deviceLength'] == pytest.approx(40.01), name
        assert h['depthMsmt'] == pytest.approx(len(tr.drill) / 100), name


@pytest.mark.parametrize('name', SAME_MEASUREMENT)
def test_to_json_reads_back(tmp_path, name):
    tr = Trace()
    tr.read(DATA / name)
    p = tmp_path / 'back.rgp'
    p.write_text(tr.to_json())
    back = Trace()
    back.read(p)
    assert back.settings['drill_depth'] == pytest.approx(tr.settings['drill_depth'])
    assert back.settings['max_drill_depth'] == pytest.approx(tr.settings['max_drill_depth'])
    assert back.drill == tr.drill
