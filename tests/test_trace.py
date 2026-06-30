#import pytest
import jsondiff as jd
from imlresi import trace


# test format identification
def test_identify_format():
    assert trace.identify_format('tests/data/1-131-withfeed-json.rgp') == 'json'
    assert trace.identify_format('tests/data/1-131-withfeed.rgp') == 'bin'
    assert trace.identify_format('tests/data/1-131-withfeed-txt1.txt') == 'txt1'
    assert trace.identify_format('tests/data/1-131-withfeed-txt2.txt') == 'txt2'
    assert trace.identify_format('tests/data/2-178-withfeed.pdc') == 'pdc'
    #assert trace.identify_format('tests/data/6-131-nofeed-withtrailingrubbish.rgp') == 'rgp'
    assert trace.identify_format('tests/data/7-561_COOCHI_203_H_01M103.pdc') == 'pdc'
    assert trace.identify_format('tests/data/8-LILLIP_20A_H_19903M39.pdc') == 'pdc'
    assert trace.identify_format('tests/data/9-HARWOO_5_H_4351TM20.pdc') == 'pdc'

# test individual format trace parsers
def test_read_xxx():
    # compare the dicts returned by each of the different read formats
    bin = trace.read_bin('tests/data/1-131-withfeed.rgp')
    bin.pop('raw')
    bin['settings'].pop('preselected_depth')

    txt1 = trace.read_txt1('tests/data/1-131-withfeed-txt1.txt')
    txt1.pop('raw')
    txt1['settings'].pop('preselected_depth')

    txt2 = trace.read_txt2('tests/data/1-131-withfeed-txt2.txt')
    txt2.pop('raw')
    txt2['settings'].pop('preselected_depth')

    jsn = trace.read_json('tests/data/1-131-withfeed-json.rgp')
    jsn.pop('raw')
    for e in (
        'deviceLength',
        'depthMode',
        'abortState',
        'feedOn',
        'ncOn',
        'ncState',
        'tiltOn',
        'tiltRelOn',
        'tiltRelAngle',
        'tiltAngle',
        'diameter',
        'preselected_depth',
    ):
        jsn['settings'].pop(e, None)

    assert bin == txt1, f".rgp BIN and .txt TXT1 differ: {jd.diff(bin, txt1, syntax='symmetric')}"
    assert bin == txt2, f".rgp BIN and .txt TXT2 differ: {jd.diff(bin, txt2, syntax='symmetric')}"
    assert bin == jsn, f".rgp BIN and .rgp JSON differ: {jd.diff(bin, jsn, syntax='symmetric')}"

    # todo: add .pdc format to the comparisons





# test the Trace class
def test_Trace():
    tr = trace.Trace()
    trfns = [
       'tests/data/1-131-withfeed-json.rgp',                #1
       'tests/data/1-131-withfeed.rgp',                     #2
       'tests/data/1-131-withfeed-txt1.txt',                #3
       'tests/data/1-131-withfeed-txt2.txt',                #4
       'tests/data/2-178-withfeed.pdc',                     #5
       'tests/data/1-131-withfeed-pdtools122.rgp',          #6
       'tests/data/1-131-withfeed-pdtools167.rgp',          #7
       'tests/data/3-131-nofeed.rgp',                       #8
       'tests/data/4-131-withfeed.rgp',                     #9
        'tests/data/5-132-withfeed.rgp',                    #10
 #       'tests/data/6-131-nofeed-withtrailingrubbish.rgp',  #11
        'tests/data/7-561_COOCHI_203_H_01M103.pdc',         #12
        'tests/data/8-LILLIP_20A_H_19903M39.pdc',           #13
        'tests/data/9-HARWOO_5_H_4351TM20.pdc',             #14
    ]
    resiIds = [
        'some-identifier',        #1
        'some-identifier',        #2
        'some-identifier',        #3
        'some-identifier',        #4
        'TEST 7',                 #5
        'some-identifier',        #6
        'some-identifier',        #7
        'FR121-10-3-24',          #8
        'T01',                    #9
        'HVP*6*15',               #10
#        "",                      #11
        "561 COOCHI 203 H 01",    #12
        "LILLIP 20A H 19903",     #13
        "HARWOO 5 H 4351T",       #14
    ]
    locations = [
        "some-location",                            #1
        "some-location",                            #2
        "some-location",                            #3
        "some-location",                            #4
        "26.06952° S, 152.77024° E (± 4.69584 m)",  #5
        "some-location",                            #6
        "some-location",                            #7
        "",                                         #8
        "",                                         #9
        "",                                         #10
 #       "",                                        #11
        "26.86938° S, 153.02545° E (± 4.74619 m)",  #12
        "25.84169° S, 152.70489° E (± 4.69549 m)",  #13
        "",                                         #14
    ]
    hashes = [
        '6b46a40e7b8cee4dc1ebb18516241ca4',   #1
        'f97b94fbd23d45dd22a2b799c0ff68ec',   #2
        'f97b94fbd23d45dd22a2b799c0ff68ec',   #3
        'f97b94fbd23d45dd22a2b799c0ff68ec',   #4
        'a07a37875ff4d4a8881b98d386a33be8',   #5
        'f97b94fbd23d45dd22a2b799c0ff68ec',   #6
        '6b46a40e7b8cee4dc1ebb18516241ca4',   #7
        '131800c773d850cec80b458690a73a87',   #8
        'b382e6e89a721a0f08110d501de1d6bb',   #9
        'c620d76d30b1862599ff3c66a0cd61eb',   #10
 #       '',                                  #11
        '',                                   #12
        '',                                   #13
        '',                                   #14
    ]
    for trfn, resiId, hash, loc in zip(trfns, resiIds, hashes, locations):
        print(trfn)
        tr.read(trfn)
        assert tr.get_resiId() == resiId
        #assert tr.hash() == hash
        assert tr.header['location']==loc


def test_accessors():
    from datetime import datetime
    tr = trace.Trace()
    tr.read('tests/data/2-178-withfeed.pdc')
    assert tr.get_resiId() == 'TEST 7'
    assert tr.get_drilltime().strftime('%Y%m%dT%H:%M:%S') == '20210330T15:20:05'
    assert tr.get_location() == '26.06952° S, 152.77024° E (± 4.69584 m)'
    assert tr.get_latlon() == (-26.06952, 152.77024, 4.69584)
    assert tr.get_tilt() == 88.8
    assert tr.get_comment() == "00-0-00-01"
    assert tr.get_remark() == "00-0-00-01"
    assert tr.get_instrument() == "PD500-0755"
    assert tr.get_feedspeed() == 200
    assert tr.get_rpm() == 3500
    assert tr.get_measnumber() == 41

    #tr.read('tests/data/1-131-')

def test_trace_str():
    tr = trace.Trace()
    tr.read('tests/data/2-178-withfeed.pdc')
    s = str(tr)
    assert "*** HEADER ***" in s
    assert "*** SETTINGS ***" in s
    assert "*** DRILL FORCE (TORQUE) ***" in s
    assert "*** FEED FORCE ***" in s


def test_trace_repr():
    tr = trace.Trace()
    tr.read('tests/data/2-178-withfeed.pdc')
    r = repr(tr)
    assert "Trace" in r
    assert "trace_filename" in r
    assert "trace_format" in r


def test_trace_to_json():
    import json
    # Test on a .pdc file
    tr = trace.Trace()
    tr.read('tests/data/2-178-withfeed.pdc')
    js = tr.to_json()
    assert isinstance(js, str)
    data = json.loads(js)
    assert "header" in data
    assert "profile" in data
    assert "drill" in data["profile"]
    assert "feed" in data["profile"]
    
    # Test on a binary .rgp file
    tr_bin = trace.Trace()
    tr_bin.read('tests/data/1-131-withfeed.rgp')
    js_bin = tr_bin.to_json()
    assert isinstance(js_bin, str)
    data_bin = json.loads(js_bin)
    assert "header" in data_bin
    assert "profile" in data_bin
    assert "drill" in data_bin["profile"]
    assert "feed" in data_bin["profile"]
