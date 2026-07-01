import os
from pathlib import Path

# Load .env file if it exists
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import pytest
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


def test_process_using_resiapi_mocked():
    from unittest.mock import patch
    tr = trace.Trace()
    tr.read('tests/data/2-178-withfeed.pdc')

    with patch('requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": "success", "ring_count": 42}

        # Test with default ctrlset
        res = tr.process_using_resiapi('https://api.example.com/resi')
        assert res["status"] == "success"
        assert res["ring_count"] == 42

        # Verify post parameters and payload
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == 'https://api.example.com/resi'

        json_payload = kwargs['json']
        # Default ctrlset should be present
        assert json_payload["RingMethod"] == "Annual"
        assert json_payload["Resource"] == "RadiataPine"
        assert json_payload["fixCoef"] is True
        assert json_payload["Standardised"] is True
        assert json_payload["BaselineMethod"] == "Linear"
        assert json_payload["TreeClass"] == "Density"
        # Trace should be present
        assert "rgp" in json_payload
        assert json_payload["rgp"]["header"]["idNumber"] == "TEST 7"


@pytest.mark.skipif(
    not os.environ.get("RESI_API_URI"),
    reason="RESI_API_URI environment variable or .env file is not set"
)
def test_process_using_resiapi_real():
    tr = trace.Trace()
    tr.read('tests/data/1-131-withfeed-pdtools167.rgp')
    api_uri = os.environ.get("RESI_API_URI")
    res = tr.process_using_resiapi(api_uri)
    assert isinstance(res, dict)


def test_new_trace_accessors():
    import numpy as np
    tr = trace.Trace()
    tr.read('tests/data/2-178-withfeed.pdc')
    
    # Verify behavior before processing
    assert tr.get_result('TraceType') is None
    
    # Mock _res API dictionary for a B-B trace
    tr._res = {
        'TraceType': 'B-B',
        'DOB': 10.0,
        'BarkThickness': 2.0,
        'UBDIA': 6.0,
        'EntryRadius': 5.0,
    }
    
    assert tr.get_tracetype() == 'B-B'
    assert tr.get_dob() == 10.0
    assert tr.get_pith() == 5.0
    
    cambial = tr.get_cambial_boundaries()
    assert cambial.entry == 2.0
    assert cambial.exit == 8.0 # BarkThickness (2) + UBDIA (6)
    
    bark = tr.get_bark_thickness()
    assert bark.entry == 2.0
    assert bark.exit == 4.0 # DOB (10) - UBDIA (6)

    # Mock _res API dictionary for a P-B trace
    tr._res = {
        'TraceType': 'P-B',
        'DBHOB': 12.0,
        'BarkThickness': 3.0,
        'UBDIA': 8.0,
        'EntryRadius': 6.0,
    }
    
    assert tr.get_tracetype() == 'P-B'
    assert tr.get_dob() == 12.0 # fallback to DBHOB
    assert tr.get_pith() == 6.0
    
    cambial_pb = tr.get_cambial_boundaries()
    assert cambial_pb.entry == 3.0
    assert cambial_pb.exit is None
    
    bark_pb = tr.get_bark_thickness()
    assert bark_pb.entry == 3.0
    assert bark_pb.exit is None

    # Test failure case when neither DOB nor DBHOB is available
    tr._res = {'TraceType': 'B-B'}
    with pytest.raises(KeyError, match="Neither DOB or DBHOB are available"):
        tr.get_dob()

    # Verify get_wood_only
    # Mock tr.drill and tr.feed to be numpy arrays
    tr.drill = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    tr.feed = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    
    # Case P-B: entry=0.1, pith=0.3
    tr._res = {
        'TraceType': 'P-B',
        'BarkThickness': 0.1,
        'EntryRadius': 0.3,
    }
    wood = tr.get_wood_only()
    # ii indices: self.x >= 0.1 and self.x <= 0.3 -> indices 1, 2, 3 (self.x = [0.0, 0.1, 0.2, 0.3, 0.4])
    assert np.array_equal(wood.x, np.array([0.1, 0.2, 0.3]))
    assert np.array_equal(wood.drill, np.array([20.0, 30.0, 40.0]))
    assert np.array_equal(wood.feed, np.array([2.0, 3.0, 4.0]))

    # Case B-B: entry=0.1, exit=0.3
    tr._res = {
        'TraceType': 'B-B',
        'BarkThickness': 0.1,
        'UBDIA': 0.2,
    }
    wood_bb = tr.get_wood_only()
    # ii indices: self.x > 0.1 and self.x < 0.3 (actually 0.30000000000000004 due to float addition) -> index 2, 3
    assert np.array_equal(wood_bb.x, np.array([0.2, 0.3]))
    assert np.array_equal(wood_bb.drill, np.array([30.0, 40.0]))
    assert np.array_equal(wood_bb.feed, np.array([3.0, 4.0]))

    # Verify check_lopsidedness warning on P-B
    tr._res['TraceType'] = 'P-B'
    assert tr.check_lopsidedness() is None

    # Case B-B for check_lopsidedness
    tr._res = {
        'TraceType': 'B-B',
        'BarkThickness': 0.0,
        'UBDIA': 0.4,
    }
    # wood_bb will contain elements 1, 2, 3 (indices > 0 and < 0.4)
    # wood_bb.x = [0.1, 0.2, 0.3]
    # wood_bb.drill = [20.0, 30.0, 40.0] -> slope = 100.0
    assert tr.check_lopsidedness(ddrill_dx_max=50.0) == True
    assert tr.check_lopsidedness(ddrill_dx_max=150.0) == False

