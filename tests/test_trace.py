#import pytest
from imlresi import trace

# test format identification
def test_identify_format():
    assert trace.identify_format('tests/data/1-131-withfeed-json.rgp') == 'json'
    assert trace.identify_format('tests/data/1-131-withfeed.rgp') == 'bin'
    assert trace.identify_format('tests/data/1-131-withfeed-txt1.txt') == 'txt1'
    assert trace.identify_format('tests/data/1-131-withfeed-txt2.txt') == 'txt2'
    assert trace.identify_format('tests/data/2-178-withfeed.pdc') == 'pdc'


# test individual format trace parsers
def test_read_xxx():
    # compare the dicts returned by each of the different read formats
    jsn = trace.read_json('tests/data/1-131-withfeed-json.rgp')
    jsn.pop('raw')
    bin = trace.read_bin('tests/data/1-131-withfeed.rgp')
    bin.pop('raw')
    assert jsn == bin, "JSON and BIN differ"
    txt1 = trace.read_txt1('tests/data/1-131-withfeed-txt1.txt')
    txt1.pop('raw')
    assert jsn == txt1, "JSON and TXT1 differ"
    txt2 = trace.read_txt2('tests/data/1-131-withfeed-txt2.txt')
    txt2.pop('raw')
    assert jsn == txt2, "JSON and TXT2 differ"
    # todo: add .pdc format to the comparisons


# test the Trace class
def test_Trace():
    tr = trace.Trace()
    trfns = [
        'tests/data/1-131-withfeed-json.rgp',
        'tests/data/1-131-withfeed.rgp',
        'tests/data/1-131-withfeed-txt1.txt',
        'tests/data/1-131-withfeed-txt2.txt',
        'tests/data/2-178-withfeed.pdc',
        'tests/data/1-131-withfeed-pdtools122.rgp',
        'tests/data/1-131-withfeed-pdtools167.rgp',
        'tests/data/3-131-nofeed.rgp',
        'tests/data/4-131-withfeed.rgp',
        'tests/data/5-132-withfeed.rgp',
    ]
    resiIds = [
        'some-identifier',
        'some-identifier',
        'some-identifier',
        'some-identifier',
        'TEST 7',
        'some-identifier',
        'some-identifier',
        'FR121-10-3-24',
        'T01',
        'HVP*6*15',
    ]
    locations = [
        "some-location",
        "some-location",
        "some-location",
        "some-location",
        "26.06952° S, 152.77024° E (± 4.69584 m)",
        "some-location",
        "some-location",
        "",
        "",
        "",
    ]
    hashes = [
        '6b46a40e7b8cee4dc1ebb18516241ca4',
        'f97b94fbd23d45dd22a2b799c0ff68ec',
        'f97b94fbd23d45dd22a2b799c0ff68ec',
        'f97b94fbd23d45dd22a2b799c0ff68ec',
        'a07a37875ff4d4a8881b98d386a33be8',
        'f97b94fbd23d45dd22a2b799c0ff68ec',
        '6b46a40e7b8cee4dc1ebb18516241ca4',
        '131800c773d850cec80b458690a73a87',
        'b382e6e89a721a0f08110d501de1d6bb',
        'c620d76d30b1862599ff3c66a0cd61eb',
    ]
    for trfn, resiId, hash, loc in zip(trfns, resiIds, hashes, locations):
        tr.read(trfn)
        assert tr.get_resiId() == resiId
        assert tr.hash() == hash
        assert tr.header['location']==loc


def test_accessors():
    from datetime import datetime
    tr = trace.Trace()
    tr.read('tests/data/2-178-withfeed.pdc')
    assert tr.get_resiId() == 'TEST 7'
    assert tr.get_drilltime().strftime('%Y%m%dT%H:%M:%S') == '20210330T15:20:05'
    assert tr.get_location() == '26.06952° S, 152.77024° E (± 4.69584 m)'
    assert tr.get_latlon() == (-26.06952, 152.77024, 4.69584)

# todo: test Trace.__str__()


# todo: test Trace.__repr__()


# todo: test Trace.to_json()
