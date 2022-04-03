#import pytest
from imlresi import trace

# test format identification
def test_identify_format():
    assert trace.identify_format('tests/data/1-json.rgp') == 'json'
    assert trace.identify_format('tests/data/1-bin.rgp') == 'bin'
    assert trace.identify_format('tests/data/1-txt1.txt') == 'txt1'
    assert trace.identify_format('tests/data/1-txt2.txt') == 'txt2'
    assert trace.identify_format('tests/data/2-pdc.pdc') == 'pdc'


# test individual format trace parsers
def test_read_xxx():
    jsn = trace.read_json('tests/data/1-json.rgp')
    jsn['settings'].pop('raw')
    bin = trace.read_bin('tests/data/1-bin.rgp')
    bin['settings'].pop('raw')
    assert jsn == bin, "JSON and BIN differ"
    txt1 = trace.read_txt1('tests/data/1-txt1.txt')
    txt1['settings'].pop('raw')
    assert jsn == txt1, "JSON and TXT1 differ"
    txt2 = trace.read_txt2('tests/data/1-txt2.txt')
    txt2['settings'].pop('raw')
    assert jsn == txt2, "JSON and TXT2 differ"

    # todo: find an equivalent pair of PDC and JSON trace files
    # jsn = trace.read_json('tests/data/2-json.rgp')
    # jsn['settings'].pop('raw')
    # pdc = trace.read_pdc('tests/data/2-pdc.pdc')
    # pdc['settings'].pop('raw')
    # assert jsn == pdc, "JSON and PDC differ"


# test the Trace class
def test_Trace():
    tr = trace.Trace()
    trfns_resiId_hash = (
        ('tests/data/1-json.rgp', 'some-identifier', 'bb5dccf966861934dc59d1df70204238'),
        ('tests/data/1-bin.rgp',  'some-identifier', 'bb5dccf966861934dc59d1df70204238'),
        ('tests/data/1-txt1.txt', 'some-identifier', 'bb5dccf966861934dc59d1df70204238'),
        ('tests/data/1-txt2.txt', 'some-identifier', 'bb5dccf966861934dc59d1df70204238'),
        ('tests/data/2-pdc.pdc',  'TEST 7',          '0936d19f0c701decd51d32b757c447bc'),
    )
    for trfn, resiId, hash in trfns_resiId_hash:
        tr.read(trfn)
        assert tr.get_resiId() == resiId
        assert tr.hash() == hash


# todo: test Trace.__str__()


# todo: test Trace.__repr__()


# todo: test Trace.to_json()
