#!/usr/bin/env python3
"""
***** THIS SOFTWARE IS UNOFFICAL AND HAS NOTHING TO DO WITH IML *****

History:

* Originally developed as rgp.py for ResiImportApp.
* Adapted for use with HQPupdater
* Used with OFO1 data loading
* Transition to PyPi package


jh, Mar 2022
jh, Jun 2021
jh, Jun 2020
jh, June 2016
"""

from struct import unpack
import logging


def identify_format(fn):
    """
    Identify the trace file format
    """
    with open(fn, 'rb') as f:
        byte1 = bytes(f.read(1))
    with open(fn, 'rb') as f:
        byte1 = bytes(f.read(1))
    if byte1 == b'\x12':
        fmt = 'bin'
    elif byte1 == b'\x7b':  # '{'=='\x7b'
        fmt = 'json'
    else:
        with open(fn, 'rb') as f:
            line1 = f.readline().strip()
        if line1 == b'0F02':
            fmt = 'txt2'
        else:
            fmt = 'txt1'

    return fmt


def read_bin(fn):
    """Read a trace (*.rgp) stored in the binary format IML used until firmware
    version 1.32.

    Todo:
    * find an authoritative marker in the data declaring
      the presence of feed force data
    """

    def get_next_nbyte_string(f):
        nbytes, = unpack("<B", f.read(1))
        return f.read(nbytes).decode()

    def read_settings(b):
        return {
            # 'raw': b.decode(),
            'max_drill_depth':      unpack('<I', b[:4])[0],
            'depth_mode':           unpack('<B', b[4:5])[0],  # this is just a guess; need to set this in instrument and check
            'preselected_depth':    unpack('<I', b[5:9])[0],  # this is just a guess; need to set this in instrument and check
            'drill_depth':          unpack('<I', b[9:13])[0]/10., # mm
            'feed_speed':           unpack('<I', b[13:17])[0]/10.,
            'resolution_amplitude': unpack('<I', b[17:21])[0],
            'samples_per_mm':       float(unpack('<B', b[21:22])[0]),
            'drill_motor_offset':   unpack('<I', b[29:33])[0],
            'feed_motor_offset':    unpack('<I', b[33:37])[0],
            'needle_speed':         unpack('<I', b[60:64])[0],
            'max_feed_amplitude':  unpack('<I', b[64:68])[0]/100,
            'max_drill_amplitude':   unpack('<I', b[68:72])[0]/100,
            'abort_reason':         unpack('<B', b[72:73])[0],
            'diameter_cm':          unpack('<f', b[73:77])[0],
            'level_cm':             unpack('<f', b[77:81])[0],
            # todo: state c/check, tilt sensor, wood inspector, program etc settings
        }

    hdr = {}
    settings = {}
    torques = []
    with open(fn, 'rb') as f:
        for field in [
                'tooltype',
                'unknown1',
                'toolserial',
                'firmware_version',
                'SNRelectronic',
                'hardwareVersion',
                'date',
                'time'
        ]:
            hdr[field] = get_next_nbyte_string(f)

        # end-run around postgres not liking storing \u0000 in jsonb field
        hdr['unknown1'] = None

        hdr['measurement_number'] = unpack('<I', f.read(4))[0]
        hdr['description'] = get_next_nbyte_string(f)

        settings = f.read(81)

        for field in ['direction', 'species', 'location', 'name']:
            #hdr[field] = get_next_nbyte_string(f)
            _ = get_next_nbyte_string(f)
            # these fields are of no current interest

        # ??????
        hdr['unknown2'] = f.read(108)

        # 'Assessment Blocks'
        hdr['assessment'] = {}
        for iass in range(6):
            hdr['assessment'][iass] = [
                unpack('<ff', f.read(8)),
                get_next_nbyte_string(f)
            ]

        # comment(s)
        comment_lines = [get_next_nbyte_string(f) for icomment in range(6)]
        hdr['comment'] = "\t".join(comment_lines)

        # extract settings
        settings = read_settings(settings)

        # torque data
        # data stored as a sequence of little-endian 2-byte unsigned int
        data = f.read()
        i0 = 0
        while True:
            torques.append(unpack('<H', data[i0:i0+2])[0]/100)
            i0 += 2
            if i0+2 > len(data):
                break
        rem = data[i0:]

    # check that samples/mm * drill_depth = len(torques)
    assert len(rem) == 0, "%i bytes remain unprocessed" % len(rem)
    npts = settings['samples_per_mm']*settings['drill_depth']
    feeds = []
    if not npts == len(torques):
        if (len(torques) % npts) == 0:
            # probably the file contains feed force data
            feeds = torques[int(npts):]
            torques = torques[:int(npts)]
        else:
            logging.warning("number of data points (%i) does not match samples_per_mm*drill_depth (%i)" % (len(torques), npts))


    # drop fields that are of no interest or that have uncertain
    # correspondence to keys in JSON trace format
    hdr.pop('tooltype')
    hdr.pop('unknown1')
    hdr.pop('unknown2')
    hdr.pop('assessment')
    settings.pop('abort_reason')
    settings.pop('max_drill_depth')
    settings.pop('preselected_depth')
    settings.pop('level_cm')
    settings.pop('diameter_cm')

    # store the original file as a byte string
    with open(fn, 'rb') as f:
        settings['raw'] = f.read()

    return {
        'header': hdr,
        'drill': torques,
        'feed': feeds,
        'settings': settings
        }


def read_txt1(fn):
    """Read a trace (*.txt) exported from PD-Tools in the ASCII format IML used
    in v1.22.
    """

    def read_settings(lines):
        return {
            'raw': "\n".join(lines),
            #'max_drill_depth': int(lines[10])/100.,
            #'depth_mode': None,
            #'preselected_depth': None,
            'drill_depth':  int(lines[13])/10.,
            'feed_speed': int(lines[14])/10.,
            'resolution_amplitude': int(lines[9]),  # 10000
            'samples_per_mm': float(lines[8]),  # 010
            'drill_motor_offset': int(lines[17]),  # possibly in lines[16:19]
            'feed_motor_offset': int(lines[16]),  # possibly in lines[16:19]
            'needle_speed': int(lines[15]),
            'max_drill_amplitude': int(lines[18])/100.,  # possibly in lines[16:19]
            'max_feed_amplitude': int(lines[19])/100.,  # possibly in lines[16:19]
            #'abort_reason': None,
            #'diameter_cm': None,
            #'level_cm': None,
            'depth_mode': 0,
        }

    def read_header(lines):
        return {
            #'tooltype': None,
            'toolserial': lines[2],
            'firmware_version': lines[1],
            'SNRelectronic': lines[3],
            'hardwareVersion': lines[4],
            'date': lines[6],
            'time': lines[7],
            'measurement_number': int(lines[0]),
            'description': lines[5],
            #'direction': None,
            #'species': None,
            #'location': None,
            #'name': None,
            #'assessment': {},
            'comment': "\t".join(lines[123:129])
        }

    def read_drill_feed(lines):
        lines = lines[129:]
        if lines[0].find(';') > -1:
            # drill;feed
            drill = []
            feed = []
            for line in lines:
                d, f = line.split(';')
                drill.append(float(d)/100.)
                feed.append(float(f)/100.)
        else:
            drill = [int(x) for x in lines]
            feed = None
        return drill, feed

    lines = [line.strip() for line in open(fn, 'r')]
    drill, feed = read_drill_feed(lines)
    return {
        'header': read_header(lines),
        'drill': drill,
        'feed':  feed,
        'settings': read_settings(lines)
    }


def read_txt2(fn):
    """Read a trace (*.txt) exported from PD-Tools in the ASCII format IML used
    in v1.67
    """

    def read_settings(lines):
        return {
            'raw': "\n".join(lines),
            #'max_drill_depth': float(lines[18]),
            'depth_mode': 0, # fixme
            #'preselected_depth': None,
            'drill_depth':  float(lines[21])*10.,  # mm
            'feed_speed': float(lines[22]),
            'resolution_amplitude': int(lines[17]),
            'samples_per_mm': float(lines[16]),
            'drill_motor_offset': int(lines[25]),
            'feed_motor_offset': int(lines[24]),
            'needle_speed': int(lines[23]),
            'max_drill_amplitude': float(lines[27]),
            'max_feed_amplitude': float(lines[26]),
            #'abort_reason': None,
            #'diameter_cm': None,
            #'level_cm': None,
        }

    def read_header(lines):
        return {
            #'tooltype': None,
            'toolserial': lines[2],
            'firmware_version': lines[3],
            'SNRelectronic': lines[4],
            'hardwareVersion': lines[5],
            'date': f"{int(lines[12]):02d}.{int(lines[11]):02d}.{int(lines[10]):04d}",
            'time': f"{int(lines[13]):02d}:{int(lines[14]):02d}:{int(lines[15]):02d}",
            'measurement_number': int(lines[7]),
            'description': lines[8],
            #'direction': None,
            #'species': None,
            #'location': None,
            #'name': None,
            #'assessment': {},
            'comment': lines[9],
        }

    lines = [line.strip() for line in open(fn, 'r')]
    return {
        'header': read_header(lines),
        'drill': [float(x) for x in lines[252].split(",")],
        'feed': [float(x) for x in lines[253].split(",")],
        'settings': read_settings(lines)
    }


def read_json(fn):
    """Read a trace (*.rgp) JSON format IML used in firmwares after 1.32
    """

    def read_settings(J):
        return {'raw': J,
                #'max_drill_depth': None,
                'depth_mode': J['header']['depthMode'],
                #'preselected_depth': None,
                'drill_depth':  J['header']['depthMsmt']*10., # mm
                'feed_speed': J['header']['speedFeed'],
                'resolution_amplitude': J['header']['resolutionAmp'],
                'samples_per_mm': J['header']['resolutionAmp']/1000.,  # a total guess
                'drill_motor_offset':  J['header']['offsetDrill'],
                'feed_motor_offset':   J['header']['offsetFeed'],
                'needle_speed': J['header']['speedDrill'],
                'max_drill_amplitude': J['header']['ampMaxDrill'],  # todo: misnomer?
                'max_feed_amplitude': J['header']['ampMaxFeed'],  # todo: misnomer?
                #'abort_reason': None,
                #'diameter_cm': J['header']['diameter'], # NOT the same as diameter_cm in binary data!!!
                #'level_cm': None,
                }

    def read_header(J):
        return {
            #'tooltype': None,
            'toolserial': J['header']['snrMachine'],
            'firmware_version': J['header']['verFirmware'],
            'SNRelectronic': J['header']['snrElectronic'],
            'hardwareVersion': J['header']['verElectronic'],
            'date': '%02d.%02d.%04d' % (
                int(J['header']['dateDay']),
                int(J['header']['dateMonth']),
                int(J['header']['dateYear'])
            ),
            'time': '%02d:%02d:%02d' % (
                int(J['header']['timeHour']),
                int(J['header']['timeMinute']),
                int(J['header']['timeSecond'])
            ),
            'measurement_number': J['header']['number'],
            'description': J['header']['idNumber'],
            #'direction': None,
            #'species': None,
            #'location': None,
            #'name': None,
            #'assessment': {},
            'comment': J['header']['remark'],
        }

    import json
    s = open(fn, 'r').read()

    # when PD-Tools translates an rgp file with multi line comment
    # from binary to json formats it embeds TAB (\x09) characters in
    # the "remark field. This breaks JSON parsers.
    s = s.replace("\t","\\t")

    try:
        J = json.loads(s)
    except Exception as err:
        raise ValueError(f'{fn}:{err}. Invalid JSON?')
    assert J["device"] == "0F02"
    assert J["version"] == 2
    return {
        'header': read_header(J),
        'drill': J["profile"]["drill"],
        'feed': J["profile"]["feed"],
        'settings': read_settings(J)
    }


def init_json(mapdict, meta, data):
    """
    Initialise an object with the same structure as the json trace format.

    data can have keys drill and feed

    Todo:

    * checksums
    """
    rgp = {
        # so far everything I've seen has device=0F02 and version=2
        "device": "0F02",
        "version": 2,
        "header": {
            "snrMachine": "PD???-????",
            "verFirmware": "?.??",
            "memoryId": "????????????",
            "snrElectronic": "????? ????? ?????",
            "verElectronic": "?.?? ?.?? ?.??",
            "dateYear": 0,
            "dateMonth": 0,
            "dateDay": 0,
            "timeHour": 0,
            "timeMinute": 0,
            "timeSecond": 0,
            "number": 0,
            "idNumber": "?",  # user specified Id string
            "remark": "?",  # user specified comment string
            "deviceLength": 0.,
            "depthMode": 0,
            "depthPresel": 0.,
            "depthMsmt": 0.,
            "ampMaxFeed": 0.,
            "ampMaxDrill": 0.,
            "abortState": 0,
            "feedOn": 0,
            "ncOn": 0,
            "ncState": 0,
            "tiltOn": 0,
            "tiltRelOn": 0,
            "tiltRelAngle": 0.0,
            "tiltAngle": 0.0,
            "diameter": 0.0,
            "offsetDrill": 0,
            "offsetFeed": 0,
            "resolutionAmp": 0,
            "speedFeed": 0.,
            "speedDrill": 0,
            "resolutionFeed": 0,
            "depthPresel": 0.,
            "wiInstalled": 0,
            "wi": {
                # ...
            }
        },
        "profile": {
            'drill': [],
            'feed': []
        },
        "wiPoleResult": {
            # ...
        },
        "app": {
            # ...
        },
        "assessment": {
            # ...
        }
    }

    for k in ('drill', 'feed'):
        try:
            if data[k] is not None:
                rgp['profile'][k] = list(map(float, data[k]))
        except KeyError:
            logging.warning("missing %s data" % k)

    for k in rgp['header'].keys():
        if k not in mapdict:
            continue
        f = mapdict[k]
        if not f:
            continue
        rgp['header'][k] = f(meta)

    return rgp


class Trace():

    def __init__(self):
        self.header = {}
        self.settings = {}
        self.drill = []
        self.feed = []

    def __str__(self):
        s = '*** HEADER ***\n'
        for k, v in self.header.items():
            if (k == 'raw'):
                continue
            s += '%s: %s\n' % (k, v)
        if self.settings is not None:
            s += '*** SETTINGS ***\n'
            for k, v in self.settings.items():
                if (k[:3] == 'raw'):
                    continue
                s += '%s: %s\n' % (k, v)
        s += '*** DRILL FORCE (TORQUE) ***\n'
        if len(self.drill) > 20:
            print('%s ... %s' % (self.drill[:13], self.drill[-3:]))
        else:
            print(self.drill)
        s += '*** FEED FORCE ***\n'
        if len(self.feed) > 20:
            print('%s ... %s' % (self.drill[:13], self.drill[-3:]))
        else:
            print(self.drill)

    def __repr__(self):
        return "%s(%r)" % (self.__class__, self.__dict__)

    def read(self, trace_filename):
        """Read a trace from file.

        File Formats:

        - "bin" - a binary format for traces (*.rgp files) downloaded from
           instruments using firmware prior to 1.32
        - "json" - traces downloaded from instruments using firmware >1.32
        - "pdc" - format used by IML iPad app
        - "txt1" - txt format exported by PD-Tools v 1.22
        - "txt2" - txt format exported by PD-Tools v 1.67
        """
        self.trace_filename = trace_filename
        self.trace_format = identify_format(self.trace_filename)
        read = {
            'bin':  self.read_bin,
            'pdc':  self.read_pdc,
            'txt1': self.read_txt1,
            'txt2': self.read_txt2,
            'json': self.read_json,
            }[self.trace_format]
        res = read(self.trace_filename)
        self.header = res['header']
        self.settings = res['settings']
        self.drill = res['drill']
        self.feed = res['feed']

    def get_resiId(self):
        return self.header['description']

    def to_json(self):
        """
        Regenerate a json format trace capable of being read back into
        PD-Tools.
        """
        return init_json(
            {
                "snrMachine": lambda x: x['toolserial'],
                "verFirmware": lambda x: x['firmware_version'],
                # "memoryId": "????????????",
                "snrElectronic": lambda x: x['SNRelectronic'],
                "verElectronic": lambda x: x['hardwareVersion'],
                "dateYear": lambda x: int(x['date'].split('.')[2]),
                "dateMonth": lambda x: int(x['date'].split('.')[1]),
                "dateDay": lambda x: int(x['date'].split('.')[0]),
                "timeHour": lambda x: int(x['time'].split(':')[0]),
                "timeMinute": lambda x: int(x['time'].split(':')[1]),
                "timeSecond": lambda x: int(x['time'].split(':')[2]),
                "number": lambda x: x['measurement_number'],
                "idNumber": lambda x: x['description'],
                # "remark": "",  # user specified comment string
                "deviceLength": lambda x: x['max_drill_depth'],  # ??????
                "depthMode": lambda x: x['depth_mode'],
                "depthMsmt": lambda x: x['drill_depth'],  # ??????
                "ampMaxFeed": lambda x: x['max_feed_amplitude'],
                "ampMaxDrill": lambda x: x['max_drill_amplitude'],
                "abortState": lambda x: x['abort_reason'],
                # "feedOn": 0,
                # "ncOn": 0,
                # "ncState": 0,
                # "tiltOn": 0,
                # "tiltRelOn": 0,
                # "tiltRelAngle": 0.0,
                # "tiltAngle": 0.0,
                "diameter": lambda x: x['diameter_cm'],
                "offsetDrill": lambda x: x['drill_motor_offset'],
                "offsetFeed": lambda x: x['feed_motor_offset'],
                "resolutionAmp": lambda x: x['resolution_amplitude'],
                "speedFeed": lambda x: x['feed_speed'],
                "speedDrill": lambda x: x['needle_speed'],
                "resolutionFeed": lambda x: x['samples_per_mm'],
                "depthPresel": lambda x: x['preselected_depth'],
            },
            {
                **self.header,
                **self.settings
            },
            {
                'drill': self.drill,
                'feed': self.feed
            }
        )


if __name__ == "__main__":

    import sys
    tr = Trace()
    tr.read(sys.argv[1])
    print(tr.to_json())