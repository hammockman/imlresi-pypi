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


# test the Trace class
def test_Trace():
    pass
