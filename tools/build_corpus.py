#!/usr/bin/env python
"""Build the anonymised test corpus in tests/data/corpus/.

Usage:
    python tools/build_corpus.py --map PRIVATE_MAP.json [--out tests/data/corpus]

The map file is private (it holds the original paths and names) and is never
committed. It lists:

- ``resi_cases``: FQResi .Resi files, the df$FileName rows to keep, and the
  source trace file for each kept row;
- ``trace_cases``: rows of the archive's ``resi.raw_traces`` table (by id),
  with ``raw_source`` either ``"db"`` (use the stored ``raw`` bytes) or the
  path of the original file;
- ``db.psql_args``: how to reach the archive with psql.

Pseudonyms (instrument serials, tree ids, comments, ...) are generated
deterministically and written back into the map (``maps``) together with each
case's coordinate offset, so a rebuild reproduces the same corpus and the
mapping can be audited privately.

What is changed: file names, df$FileName and every per-trace list name, TreeID
and trace idNumber, comments/remarks, location/name strings, memoryId,
instrument serials (snrMachine/toolserial/ResiCode, snrElectronic), annotator
names, and URLs naming a host. Coordinates are shifted by one offset per case.
Measured values, settings and dates are not touched; the script re-reads every
output with imlresi and checks the drill/feed arrays are identical, then greps
the output for every original identifier.
"""
import argparse
import base64
import copy
import gzip
import hashlib
import json
import logging
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "src"))

import imlresi  # noqa: E402
from imlresi import Trace  # noqa: E402

logging.disable(logging.WARNING)

# ---------------------------------------------------------------------------
# pseudonym registry
# ---------------------------------------------------------------------------

SEP_RE = re.compile(r"([-*_ ./]+)")


class Registry:
    """Consistent original -> pseudonym maps, persisted in the private map."""

    KINDS = ("serial", "electronic", "id", "comment", "name", "location",
             "memory", "note", "annotator", "url", "filename")

    def __init__(self, saved=None):
        self.maps = {k: dict((saved or {}).get(k, {})) for k in self.KINDS}
        self.counters = {k: len(v) for k, v in self.maps.items()}

    def _get(self, kind, orig, make):
        m = self.maps[kind]
        if orig not in m:
            self.counters[kind] += 1
            m[orig] = make(self.counters[kind])
        return m[orig]

    @staticmethod
    def blank(s):
        return s is None or s.strip() == "" or set(s.strip()) <= {"?"}

    def serial(self, s):
        if self.blank(s):
            return s
        prefix = s.split("-")[0] if "-" in s else "SN"
        return self._get("serial", s, lambda i: f"{prefix}-{9000 + i:04d}")

    def electronic(self, s):
        if self.blank(s) or not re.fullmatch(r"[0-9 ]+", s):
            return self._get("electronic", s, lambda i: f"ELEC-{i:03d}") if not self.blank(s) else s

        def make(i):
            groups = s.split(" ")
            return " ".join(f"9{i:0{max(len(g) - 1, 1)}d}"[-len(g):] if g else g for g in groups)
        return self._get("electronic", s, make)

    def ident(self, s, case_no):
        """Neutral id with the same separators as the original."""
        if self.blank(s):
            return s

        def make(i):
            parts = SEP_RE.split(s.strip())
            toks = parts[0::2]
            seps = parts[1::2]
            k = len(toks)
            if k == 1:
                new = [f"TREE{i:03d}"]
            elif k == 2:
                new = [f"SITE{case_no:02d}", f"T{i:03d}"]
            elif k == 3:
                new = [f"SITE{case_no:02d}", "P01", f"T{i:03d}"]
            else:
                new = ([f"SITE{case_no:02d}", "STAND01"]
                       + [f"P{j:02d}" for j in range(1, k - 2)] + [f"T{i:03d}"])
            out = new[0]
            for sep, tok in zip(seps, new[1:]):
                out += sep + tok
            return out
        return self._get("id", s, make)

    def comment(self, s):
        """Comments may hold several tab-separated lines: map each line."""
        if s is None:
            return s
        if "\t" in s:
            return "\t".join(self.comment(x) for x in s.split("\t"))
        if self.blank(s):
            return s
        return self._get("comment", s, lambda i: f"COMMENT-{i:02d}")

    def name(self, s):
        return s if self.blank(s) else self._get("name", s, lambda i: f"NAME-{i:02d}")

    def location_text(self, s):
        return s if self.blank(s) else self._get("location", s, lambda i: f"LOCATION-{i:02d}")

    def memory(self, s):
        if self.blank(s):
            return s
        if re.fullmatch(r"\d+", s):
            return self._get("memory", s, lambda i: f"{i:0{len(s)}d}")
        return self._get("memory", s, lambda i: f"MEM{i:03d}")

    def note(self, s):
        return s if self.blank(s) else self._get("note", s, lambda i: f"NOTE-{i:02d}")

    def annotator(self, s):
        return s if self.blank(s) else self._get("annotator", s, lambda i: f"annotator-{i}")

    def url(self, s):
        if self.blank(s) or "://" not in s:
            return s
        return self._get("url", s, lambda i: re.sub(r"://[^/:]+", "://example.invalid", s))


# ---------------------------------------------------------------------------
# coordinates
# ---------------------------------------------------------------------------

LOC_RE = re.compile(
    r"(\d+(?:\.\d+)?)(\s*(?:°|\\u00b0|\\u00B0)\s*)([NS])(\s*,\s*)"
    r"(\d+(?:\.\d+)?)(\s*(?:°|\\u00b0|\\u00B0)\s*)([EW])")


def choose_offset(lat, lon, rng):
    """Magnitude offsets (dlat, dlon) that move a point off-shore.

    Applied as |v| + d with the hemisphere kept. Eastern Australia goes east
    into the Pacific, western Australia west into the Indian Ocean, New
    Zealand west into the Tasman Sea.
    """
    alon = abs(lon)
    dlat = rng.uniform(-1.0, 1.0)
    if lon >= 0 and 140 <= alon < 160:
        dlon = rng.uniform(5.0, 8.0)
    elif lon >= 0 and 160 <= alon <= 180:
        dlon = -rng.uniform(6.0, 9.0)
    elif lon >= 0 and alon < 130:
        dlon = -rng.uniform(6.0, 9.0)
    else:
        dlon = rng.uniform(5.0, 8.0)
    return [round(dlat, 5), round(dlon, 5)]


def shift_decimal_str(num, d):
    dec = len(num.split(".")[1]) if "." in num else 0
    q = Decimal(1).scaleb(-dec)
    v = (Decimal(num) + Decimal(str(d))).quantize(q)
    if v <= 0:
        raise ValueError("coordinate offset would flip hemisphere")
    return f"{v:.{dec}f}"


def find_latlon(s):
    m = LOC_RE.search(s or "")
    if not m:
        return None
    lat = float(m.group(1)) * (-1 if m.group(3) == "S" else 1)
    lon = float(m.group(5)) * (-1 if m.group(7) == "W" else 1)
    return lat, lon


def shift_location(s, off):
    """Shift every 'dd.ddddd° S, ddd.ddddd° E' in s; keep everything else."""
    def rep(m):
        return (shift_decimal_str(m.group(1), off[0]) + m.group(2) + m.group(3) + m.group(4)
                + shift_decimal_str(m.group(5), off[1]) + m.group(6) + m.group(7))
    return LOC_RE.sub(rep, s)


class Ctx:
    """Per-case anonymisation context."""

    def __init__(self, reg, case_no, offset):
        self.reg = reg
        self.case_no = case_no
        self.offset = offset
        self.log = []          # (field, old, new)

    def location(self, s):
        if Registry.blank(s):
            return s
        if LOC_RE.search(s):
            if self.offset is None:
                raise RuntimeError("coordinates found but no offset chosen")
            new = shift_location(s, self.offset)
        else:
            new = self.reg.location_text(s)
        return new

    def field(self, key, s):
        """Map one header string by its field name."""
        r = self.reg
        f = {
            "snrMachine": r.serial, "toolserial": r.serial,
            "snrElectronic": r.electronic, "SNRelectronic": r.electronic,
            "memoryId": r.memory,
            "idNumber": lambda v: r.ident(v, self.case_no),
            "description": lambda v: r.ident(v, self.case_no),
            "remark": r.comment, "comment": r.comment,
            "location": self.location,
            "name": r.name,
            "assessment": r.note,
        }[key]
        new = f(s)
        if new != s:
            self.log.append((key, s, new))
        return new


# ---------------------------------------------------------------------------
# trace rewriting
# ---------------------------------------------------------------------------

JSON_HEADER_KEYS = ("snrMachine", "snrElectronic", "memoryId", "idNumber",
                    "remark", "location", "name")
STR_LIT = r'"((?:[^"\\]|\\.)*)"'
# string leaves that are kept verbatim (not identifying)
KEEP_STRING_KEYS = {"device", "verFirmware", "verElectronic", "dateTime",
                    "nextService", "direction", "species", "TraceType",
                    "trace_type", "truly_radial", "ugliness", "type"}


def decode_lit(lit):
    return json.loads('"' + lit.replace("\t", "\\t") + '"')


def encode_like(new, old_lit):
    enc = json.dumps(new, ensure_ascii=False)[1:-1]
    if "\t" in old_lit:          # PD-Tools writes raw TABs in remarks
        enc = enc.replace("\\t", "\t")
    return enc


def sniff_location_coords(raw_text):
    for m in re.finditer(r'"location"\s*:\s*' + STR_LIT, raw_text):
        ll = find_latlon(decode_lit(m.group(1)))
        if ll:
            return ll
    return None


def _rewrite_array(text, key, fn_by_index):
    """Rewrite string elements of the JSON array value(s) of `key`."""
    def rep_array(m):
        body = m.group(2)
        out, pos, i = [], 0, 0
        for em in re.finditer(STR_LIT + r'|[^,\s\]]+', body):
            out.append(body[pos:em.start()])
            tok = em.group(0)
            if tok.startswith('"'):
                old = decode_lit(em.group(1))
                new = fn_by_index(i, old)
                tok = '"' + (encode_like(new, em.group(1)) if new != old else em.group(1)) + '"'
            out.append(tok)
            pos = em.end()
            i += 1
        out.append(body[pos:])
        return m.group(1) + "".join(out) + m.group(3)
    return re.sub(r'("' + key + r'"\s*:\s*\[)(.*?)(\])', rep_array, text, flags=re.S)


def rewrite_json_text(text, ctx):
    for key in JSON_HEADER_KEYS:
        def rep(m, key=key):
            old_lit = m.group(2)
            old = decode_lit(old_lit)
            if key == "location" and LOC_RE.search(old_lit):
                # edit the numbers inside the literal to keep its escaping
                new_lit = shift_location(old_lit, ctx.offset)
                ctx.log.append((key, old, decode_lit(new_lit)))
                return m.group(1) + '"' + new_lit + '"'
            new = ctx.field(key, old)
            if new == old:
                return m.group(0)
            return m.group(1) + '"' + encode_like(new, old_lit) + '"'
        text = re.sub(r'("' + key + r'"\s*:\s*)' + STR_LIT, rep, text)

    # app/object: [?, direction, species, location, name]
    def obj(i, old):
        if i == 3:
            return ctx.field("location", old)
        if i == 4:
            return ctx.field("name", old)
        return old
    text = _rewrite_array(text, "object", obj)
    # app/assessment/text: free text notes
    text = _rewrite_array(text, "text", lambda i, old: ctx.field("assessment", old))
    return text


def anonymise_json_dict(J, ctx):
    """Apply the same field mapping to a parsed trace (the archive's jsonb)."""
    J = copy.deepcopy(J)
    h = J.get("header", {})
    for key in JSON_HEADER_KEYS:
        if isinstance(h.get(key), str):
            h[key] = ctx.field(key, h[key])
    app = J.get("app") or {}
    obj = app.get("object")
    if isinstance(obj, list):
        if len(obj) > 3 and isinstance(obj[3], str):
            obj[3] = ctx.field("location", obj[3])
        if len(obj) > 4 and isinstance(obj[4], str):
            obj[4] = ctx.field("name", obj[4])
    ass = app.get("assessment") or {}
    if isinstance(ass.get("text"), list):
        ass["text"] = [ctx.field("assessment", t) if isinstance(t, str) else t for t in ass["text"]]
    return J


def rewrite_bin(raw, ctx):
    """Re-emit a pre-1.32 binary .rgp with replaced header strings."""
    pos = 0
    out = bytearray()

    def take(n):
        nonlocal pos
        b = raw[pos:pos + n]
        if len(b) != n:
            raise ValueError("truncated binary header")
        pos += n
        return b

    def pstr():
        n = take(1)[0]
        return take(n)

    def emit_str(b, field=None):
        if field is not None:
            s = b.decode("latin-1")
            new = ctx.field(field, s)
            if new != s:
                b = new.encode("latin-1")
        if len(b) > 255:
            raise ValueError("string too long for 1-byte length prefix")
        out.append(len(b))
        out.extend(b)

    for f in ("tooltype", "unknown1", "toolserial", "firmware_version",
              "SNRelectronic", "hardwareVersion", "date", "time"):
        emit_str(pstr(), {"toolserial": "toolserial", "SNRelectronic": "SNRelectronic"}.get(f))
    out.extend(take(4))                        # measurement number
    emit_str(pstr(), "description")
    out.extend(take(81))                       # settings
    for f in ("direction", "species", "location", "name"):
        emit_str(pstr(), {"location": "location", "name": "name"}.get(f))
    out.extend(take(108))                      # unknown2
    for _ in range(6):                         # assessment blocks
        out.extend(take(8))
        emit_str(pstr(), "assessment")
    for _ in range(6):                         # comment lines
        emit_str(pstr(), "comment")
    out.extend(raw[pos:])                      # uint16 data, untouched
    return bytes(out), len(raw) - pos


def rewrite_txt1(raw, ctx):
    text = raw.decode("latin-1")
    lines = text.splitlines(keepends=True)

    def body(i):
        return lines[i].rstrip("\r\n")

    def put(i, new):
        ending = lines[i][len(body(i)):]
        lines[i] = new + ending

    put(2, ctx.field("toolserial", body(2)))
    put(3, ctx.field("SNRelectronic", body(3)))
    put(5, ctx.field("description", body(5)))
    put(115, ctx.field("location", body(115)))
    put(116, ctx.field("name", body(116)))
    for i in range(117, 123):                  # "00000-00000: text"
        b = body(i)
        if ": " in b:
            head, txt = b.split(": ", 1)
            put(i, head + ": " + ctx.field("assessment", txt))
    for i in range(123, 129):
        put(i, ctx.field("comment", body(i)))
    return "".join(lines).encode("latin-1")


def trace_format(raw):
    if raw[:1] == b"\x12":
        return "bin"
    if raw[:1] == b"{":
        return "json"
    if raw.split(b"\n", 1)[0].strip() == b"0F02":
        return "txt2"
    return "txt1"


def rewrite_trace(raw, ctx):
    fmt = trace_format(raw)
    if fmt == "bin":
        new, ndata = rewrite_bin(raw, ctx)
        assert new[-ndata:] == raw[-ndata:]
        return new, fmt
    if fmt == "json":
        text = raw.decode("utf-8", errors="surrogateescape")
        new = rewrite_json_text(text, ctx)
        return new.encode("utf-8", errors="surrogateescape"), fmt
    if fmt == "txt1":
        return rewrite_txt1(raw, ctx), fmt
    raise NotImplementedError(fmt)


def trace_coords(raw):
    fmt = trace_format(raw)
    if fmt == "json":
        return sniff_location_coords(raw.decode("utf-8", errors="replace"))
    return find_latlon(raw.decode("latin-1"))


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------

ANON_HEADER_KEYS = {"toolserial", "SNRelectronic", "description", "location",
                    "name", "comment"}


def read_trace(path):
    t = Trace()
    t.read(str(path))
    return t


def compare_traces(orig_path, new_path):
    a, b = read_trace(orig_path), read_trace(new_path)
    problems = []
    if list(a.drill) != list(b.drill):
        problems.append("drill differs")
    if list(a.feed or []) != list(b.feed or []):
        problems.append("feed differs")
    if a.settings != b.settings:
        problems.append("settings differ")
    for k in set(a.header) | set(b.header):
        if k in ANON_HEADER_KEYS:
            continue
        if a.header.get(k) != b.header.get(k):
            problems.append(f"header {k} differs")
    return b, problems


def string_leaves(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from string_leaves(v, f"{path}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from string_leaves(v, f"{path}[{i}]")
    elif isinstance(o, str):
        yield path, o


def unreviewed_strings(J, reg):
    """String leaves that are neither whitelisted, blank nor a pseudonym."""
    pseud = {v for m in reg.maps.values() for v in m.values()}
    bad = []
    for path, s in string_leaves(J):
        key = re.sub(r"\[\d+\]$", "", path).rsplit("/", 1)[-1]
        if Registry.blank(s) or key in KEEP_STRING_KEYS:
            continue
        if re.search(r"/object\[[012]\]$", path):
            continue
        if s in pseud or all(x in pseud or Registry.blank(x) for x in s.split("\t")):
            continue
        if find_latlon(s):
            continue          # shifted coordinates (checked separately)
        if re.fullmatch(r"[a-z][a-z-]*", s) and ("/annotation" in path or path.startswith("/annotations")):
            continue          # annotation vocabulary (bark, pith, close-to-pith, ...)
        bad.append((path, s))
    return bad


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------

class DB:
    def __init__(self, args):
        self.args = ["psql", "-X", "-A", "-t", "-q"] + list(args)

    def query(self, sql):
        r = subprocess.run(self.args + ["-c", sql], capture_output=True, text=True, check=True)
        return r.stdout.strip()

    def trace_row(self, db_id):
        sql = f"""select json_build_object(
            'tracefilename', tracefilename, 'trialid', trialid, 'species', species,
            'trace', trace, 'feature_locations', feature_locations,
            'annotations', (select coalesce(json_agg(json_build_object(
                'annotation', annotation, 'annotator', annotator) order by id), '[]'::json)
                from resi.raw_annotations a where a.traceid = t.id))::text
            from resi.raw_traces t where id = {int(db_id)}"""
        return json.loads(self.query(sql))

    def raw(self, db_id):
        b64 = self.query(f"select encode(raw, 'base64') from resi.raw_traces where id = {int(db_id)}")
        return base64.b64decode(b64)


def rds_format(path):
    """(compress, version) of an RDS file, for saveRDS()."""
    with open(path, "rb") as f:
        head = f.read(6)
    if head[:2] == b"\x1f\x8b":
        comp, data = "gzip", gzip.open(path).read(16)
    elif head[:3] == b"BZh":
        import bz2
        comp, data = "bzip2", bz2.open(path).read(16)
    elif head[:6] == b"\xfd7zXZ\x00":
        import lzma
        comp, data = "xz", lzma.open(path).read(16)
    else:
        comp, data = False, head + open(path, "rb").read(16)[6:]
    if data[:2] not in (b"X\n", b"B\n", b"A\n"):
        raise ValueError(f"unknown RDS serialisation in {path}")
    if data[:2] != b"X\n":
        raise NotImplementedError("non-XDR RDS")
    version = struct.unpack(">i", data[2:6])[0]
    return comp, version


def rds_bytes(path):
    with open(path, "rb") as f:
        head = f.read(2)
    return gzip.open(path).read() if head == b"\x1f\x8b" else open(path, "rb").read()


def L(x):
    """jsonlite unboxes length-1 vectors; make them lists again."""
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def run_r(spec, tmp):
    spec_path = Path(tmp) / "spec.json"
    rep_path = Path(tmp) / "report.json"
    spec_path.write_text(json.dumps(spec))
    r = subprocess.run(["Rscript", str(HERE / "anonymise_resi.R"), str(spec_path), str(rep_path)],
                       capture_output=True, text=True)
    report = json.loads(rep_path.read_text()) if rep_path.exists() else None
    if r.returncode != 0:
        raise RuntimeError(f"anonymise_resi.R failed ({r.returncode}): {r.stderr[-2000:]}")
    return report


def rdata_check(path):
    import warnings
    import rdata
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            rdata.conversion.convert(rdata.parser.parse_file(str(path)))
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def resiresultset_check(path):
    import warnings
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rs = imlresi.ResiResultSet()
            rs.load(str(path))
        return True, None, rs, [str(x.message) for x in w]
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}", None, []


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def build_resi_case(case, case_no, reg, out_root, tmp, rng, originals):
    cid = case["id"]
    src = case["source"]
    cdir = out_root / "resi" / cid
    tdir = cdir / "traces"
    tdir.mkdir(parents=True, exist_ok=True)

    probe = run_r({"src": src, "out": "", "probe": True}, tmp)
    vals = probe["values"]
    keep = case["rows"]

    # trace file names and sources
    fn_map = {}
    for j, fn in enumerate(keep, 1):
        ext = Path(case["traces"][fn]).suffix
        fn_map[fn] = f"{cid}_{j:02d}{ext}"
        reg.maps["filename"][fn] = fn_map[fn]

    # coordinates: from the .Resi or from the traces
    raws = {fn: Path(case["traces"][fn]).read_bytes() for fn in keep}
    if "latlon_offset" not in case:
        ll = None
        for fn in keep:
            ll = ll or trace_coords(raws[fn])
        if ll is None:
            lat = [v for v in L(vals.get("df", {}).get("Lat")) if v not in (None, "NA", "NaN", "Not Available")]
            lon = [v for v in L(vals.get("df", {}).get("Lon")) if v not in (None, "NA", "NaN", "Not Available")]
            try:
                la, lo = float(lat[0]), float(lon[0])
                if la != 0 and lo != 0:
                    ll = (la, lo)
            except (IndexError, ValueError):
                pass
        case["latlon_offset"] = choose_offset(*ll, rng) if ll else None
    offset = case["latlon_offset"]
    ctx = Ctx(reg, case_no, offset)

    # traces first, so idNumber/remark pseudonyms line up with TreeID/Comment
    trace_info = []
    for fn in keep:
        raw = raws[fn]
        new, fmt = rewrite_trace(raw, ctx)
        out = tdir / fn_map[fn]
        out.write_bytes(new)
        orig_tmp = Path(tmp) / ("orig_" + fn_map[fn])
        orig_tmp.write_bytes(raw)
        t, problems = compare_traces(orig_tmp, out)
        originals.add_trace(raw, fn)
        trace_info.append({"file": fn_map[fn], "format": t.trace_format, "problems": problems,
                           "instrument": t.header.get("toolserial"),
                           "firmware": t.header.get("firmware_version"),
                           "has_feed": bool(t.feed) and any(x != 0 for x in t.feed),
                           "location": t.header.get("location")})

    # column maps for every data.frame element
    col_maps = {}
    for el, cols in vals.items():
        for cn, vs in cols.items():
            for v in L(vs):
                if v is None:
                    continue
                if cn == "TreeID":
                    new = reg.ident(v, case_no)
                elif cn == "ResiCode":
                    new = reg.serial(v)
                elif cn == "Comment":
                    new = reg.comment(v)
                elif cn == "WebSite":
                    new = reg.url(v)
                else:
                    continue
                if new != v:
                    col_maps.setdefault(cn, {})[v] = new
                if cn != "WebSite" or new != v:   # app labels (FWPA/FQ) are kept
                    originals.add(v)
    for fn in L(probe["FileName"]):
        originals.add(fn)
        originals.add(Path(fn).stem)
    for fn in keep:
        originals.add(Path(case["traces"][fn]).name)
        originals.add(Path(case["traces"][fn]).stem)
    originals.add(Path(src).name)
    originals.add(Path(src).stem)

    comp, ver = rds_format(src)
    out_resi = cdir / f"{cid}.Resi"
    report = run_r({"src": src, "out": str(out_resi), "keep": keep, "filename_map": fn_map,
                    "column_maps": col_maps, "latlon_offset": offset,
                    "compress": comp, "version": ver,
                    "strip_reactive_dependents": bool(probe.get("reactivevalues"))}, tmp)
    rd_ok, rd_err = rdata_check(out_resi)
    rd_ok_orig, rd_err_orig = rdata_check(src)
    rs_ok, rs_err, rs, rs_warn = resiresultset_check(out_resi)

    # .Resi coordinates must agree with the shifted trace locations
    coord_check = None
    if offset is not None and rs is not None:
        coord_check = []
        for r_ in rs.results:
            ti = next(x for x in trace_info if x["file"] == r_.filename)
            ll = find_latlon(ti["location"] or "")
            d = r_.descriptors
            if ll is not None and d.get("Lat") is not None:
                coord_check.append(abs(abs(float(d["Lat"])) - abs(ll[0])) < 1e-9
                                   and abs(abs(float(d["Lon"])) - abs(ll[1])) < 1e-9)

    # drill arrays in the .Resi vs the copied traces (informational: the app
    # may trim or rescale traces, so this is not required to hold)
    drill_vs_trace = None
    if rs is not None:
        drill_vs_trace = {}
        for r_ in rs.results:
            p = tdir / r_.filename
            if p.exists() and r_.drill is not None:
                t = read_trace(p)
                drill_vs_trace[r_.filename] = (len(r_.drill) == len(t.drill)
                                               and bool((abs(r_.drill - __import__("numpy").array(t.drill)) < 1e-6).all()))

    s = report["summary"]
    notes = []
    for el, how in report["actions"].items():
        if "extra" in how or "constant table" in how or ("named" in how and f"kept {len(keep)} of" not in how):
            notes.append(f"{el}: {how}")
    if report.get("reactivevalues"):
        notes.append("saved by an old Shiny app as a reactivevalues object (R6/environments); "
                     "anonymised in place inside its .values environment. Its reactive dependency "
                     "registry (impl$.dependents, Shiny contexts capturing the whole server "
                     "environment incl. source code and local paths) was emptied; everything else, "
                     "including the R6 object and its methods, is as saved")
        if rd_ok_orig is False and rd_ok is False:
            notes.append(f"rdata fails on the original ({rd_err_orig}) and on this file ({rd_err})")
    for ti in trace_info:
        if Path(ti["file"]).suffix.lower() != Path(next(k for k, v in fn_map.items() if v == ti["file"])).suffix.lower():
            notes.append(f"df$FileName originally named a {Path(next(k for k, v in fn_map.items() if v == ti['file'])).suffix} "
                         f"export of this trace; it now names the source {Path(ti['file']).suffix} file")
            break
    if any(ti["format"] in ("json", "pdc") for ti in trace_info):
        notes.append("JSON trace checksum fields are the originals and no longer match the edited text")
    return {
        "id": cid,
        "kind": "resi",
        "path": f"resi/{cid}/{cid}.Resi",
        "format": "RDS (saveRDS, %s, version %d)" % ("gzip" if comp == "gzip" else comp, ver),
        "app_version": (L(s["version"]) or [None])[0],
        "df_version_column": (L(vals.get("df", {}).get("Version")) or [None])[0],
        "df_columns": L(s["df_columns"]),
        "n_df_columns": len(L(s["df_columns"])),
        "top_level_elements": L(report["top_level"]),
        "nonempty_elements": L(s["nonempty"]),
        "n_traces": report["n_after"],
        "trace_files": [ti["file"] for ti in trace_info],
        "trace_formats": sorted({ti["format"] for ti in trace_info}),
        "trace_types": L(s["TraceType"]),
        "instruments": sorted(set(L(s["ResiCode"])) | {ti["instrument"] for ti in trace_info}),
        "firmware": sorted({ti["firmware"] for ti in trace_info}),
        "resource": L(s["Resource"]),
        "has_feed": bool(s["has_feed"]),
        "traces_have_feed": any(ti["has_feed"] for ti in trace_info),
        "den_traces": bool(s["den_traces"]),
        "cum_den_traces": bool(s["cum_den_traces"]),
        "coordinates_shifted": offset is not None,
        "rdata_loads": rd_ok,
        "rdata_error": rd_err,
        "rdata_loads_original": rd_ok_orig,
        "resiresultset_loads": rs_ok,
        "resiresultset_error": rs_err,
        "resiresultset_warnings": sorted(set(re.sub(r"in \S+\.Resi", "in <file>", w) for w in rs_warn)),
        "resi_drill_equals_trace_drill": drill_vs_trace,
        "coordinates_consistent": coord_check,
        "element_actions": report["actions"],
        "trace_check_problems": {ti["file"]: ti["problems"] for ti in trace_info if ti["problems"]},
        "notes": notes,
    }, report


def build_trace_case(tc, case_no, reg, db, out_root, tmp, rng, originals):
    tid = tc["id"]
    case_no = int(tid[1:])
    row = db.trace_row(tc["db_id"])
    if tc["raw_source"] == "db":
        raw = db.raw(tc["db_id"])
    else:
        raw = Path(tc["raw_source"]).read_bytes()
        originals.add(Path(tc["raw_source"]).name)
        originals.add(Path(tc["raw_source"]).stem)
    ext = Path(row["tracefilename"]).suffix.lower() or ".rgp"
    for p in [row["tracefilename"]]:
        originals.add(Path(p).name)
        originals.add(Path(p).stem)
    originals.add_trace(raw, Path(row["tracefilename"]).name)

    if "latlon_offset" not in tc:
        ll = trace_coords(raw)
        tc["latlon_offset"] = choose_offset(*ll, rng) if ll else None
    ctx = Ctx(reg, case_no, tc["latlon_offset"])

    tdir = out_root / "traces"
    tdir.mkdir(parents=True, exist_ok=True)
    new, fmt = rewrite_trace(raw, ctx)
    out = tdir / f"{tid}{ext}"
    out.write_bytes(new)
    orig_tmp = Path(tmp) / f"orig_{tid}{ext}"
    orig_tmp.write_bytes(raw)
    t, problems = compare_traces(orig_tmp, out)

    expected = anonymise_json_dict(row["trace"], ctx)
    (tdir / f"{tid}.expected.json").write_text(
        json.dumps(expected, separators=(",", ":"), ensure_ascii=False) + "\n")
    current = json.loads(t.to_json())
    expected_matches = current == expected

    ann = None
    if row["feature_locations"] is not None or row["annotations"]:
        anns = []
        for a in row["annotations"]:
            an = copy.deepcopy(a["annotation"])
            if "traceid" in an:
                an["traceid"] = None
            if isinstance(an.get("scan"), str):
                an["scan"] = reg.ident(an["scan"], case_no)
            anns.append({"annotator": reg.annotator(a["annotator"]), "annotation": an})
        ann = {"feature_locations": row["feature_locations"], "annotations": anns}
        (tdir / f"{tid}.annotation.json").write_text(json.dumps(ann, indent=1, ensure_ascii=False) + "\n")

    bad = unreviewed_strings(json.loads(new.decode("utf-8", "replace")), reg) if fmt == "json" else []
    bad += [("expected" + p, s) for p, s in unreviewed_strings(expected, reg)]
    if ann:
        bad += [("annotation" + p, s) for p, s in unreviewed_strings(ann, reg)]

    tfmt = t.trace_format
    notes = []
    if tc["raw_source"] != "db":
        notes.append("archive row has no raw bytes; original file taken from the file share "
                     "(drill array identical to the archived trace)")
    if tfmt in ("json", "pdc"):
        notes.append("JSON checksum fields are the originals and no longer match the edited text")
    if not expected_matches:
        diff_keys = sorted(k for k in set(current) | set(expected) if current.get(k) != expected.get(k))
        notes.append("expected.json (archived parse) differs from the current reader's to_json() "
                     f"in: {', '.join(diff_keys)}")
    if ann and any("traceid" in a["annotation"] for a in ann["annotations"]):
        notes.append("annotation traceid (archive row id) set to null")

    return {
        "id": tid,
        "kind": "trace",
        "path": f"traces/{tid}{ext}",
        "format": tfmt,
        "extension": ext,
        # selection label without archive trial ids
        "selected_as": re.sub(r"\s+(t\d+|notrial)\b", "", tc.get("stratum") or "").strip() or None,
        "firmware": t.header.get("firmware_version"),
        "instruments": [t.header.get("toolserial")],
        "species": row["species"] or (t.header.get("species") or None),
        "n_drill": len(t.drill),
        "has_feed": bool(t.feed) and any(x != 0 for x in t.feed),
        "has_expected_json": True,
        "expected_equals_current_reader": expected_matches,
        "has_feature_locations": row["feature_locations"] is not None,
        "n_annotations": len(row["annotations"]),
        "coordinates_shifted": tc["latlon_offset"] is not None,
        "trace_check_problems": problems,
        "unreviewed_strings": bad,
        "notes": notes,
    }


class Originals:
    """Every original identifier, for the final grep."""

    def __init__(self):
        self.items = set()

    def add(self, s):
        if s is None:
            return
        s = str(s).strip()
        if len(s) >= 4 and not Registry.blank(s) and not re.fullmatch(r"[\d.\- ]{1,6}", s):
            self.items.add(s)

    def add_trace(self, raw, name):
        """Header strings of an original trace."""
        try:
            fmt = trace_format(raw)
            with tempfile.NamedTemporaryFile(suffix=Path(name).suffix) as f:
                f.write(raw)
                f.flush()
                t = read_trace(f.name)
            h = t.header
            for k in ("toolserial", "SNRelectronic", "description", "location", "name"):
                self.add(h.get(k))
            for line in (h.get("comment") or "").split("\t"):
                self.add(line)
            ll = find_latlon(h.get("location") or "")
            if ll:
                m = LOC_RE.search(h["location"])
                self.add(m.group(1))
                self.add(m.group(5))
            if fmt == "json":
                J = json.loads(raw.decode("utf-8", "replace").replace("\t", "\\t"))
                self.add(J.get("header", {}).get("memoryId"))
        except Exception as e:  # noqa: BLE001
            print(f"warning: could not collect identifiers from {name}: {e}", file=sys.stderr)


def grep_outputs(out_root, originals, reg):
    pseud = {v for m in reg.maps.values() for v in m.values()}
    needles = sorted(s for s in originals.items if s not in pseud)
    hits = []
    for p in sorted(out_root.rglob("*")):
        if not p.is_file():
            continue
        data = rds_bytes(p) if p.suffix == ".Resi" else p.read_bytes()
        for s in needles:
            for enc in {s.encode("utf-8"), s.encode("latin-1", "ignore")}:
                if enc and enc in data:
                    hits.append((str(p.relative_to(out_root)), s))
                    break
    return needles, hits


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", required=True, help="private mapping file (read and updated)")
    ap.add_argument("--out", default=str(REPO / "tests" / "data" / "corpus"))
    ap.add_argument("--only", nargs="*", help="build only these case ids (no manifest/grep)")
    args = ap.parse_args()

    map_path = Path(args.map)
    M = json.loads(map_path.read_text())
    reg = Registry(M.get("maps"))
    rng = random.Random(M.get("seed", 0))
    db = DB(M["db"]["psql_args"])
    out_root = Path(args.out)
    if not args.only and out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    originals = Originals()

    manifest = {"description": "Anonymised FQResi .Resi files and IML Resistograph traces "
                               "for imlresi tests. Built by tools/build_corpus.py.",
                "anonymisation": [
                    "file names, df$FileName and per-trace list names are C<nn>_<mm>.<ext> or T<nnn>.<ext>",
                    "TreeID/idNumber replaced by neutral ids with the original separators",
                    "comments/remarks, names, non-coordinate locations, memoryId, assessment texts and "
                    "annotators replaced by placeholders",
                    "instrument serials (ResiCode/snrMachine/toolserial) mapped to PD400-9xxx/PD500-9xxx, "
                    "snrElectronic to 9xxxx groups, consistently across .Resi files and traces",
                    "coordinates shifted by one random offset per case (off-shore); string formats kept",
                    "dates, settings, species, direction and all measured values unchanged",
                ],
                "cases": []}
    reports = {}
    with tempfile.TemporaryDirectory() as tmp:
        for case_no, case in enumerate(M["resi_cases"], 1):
            if args.only and case["id"] not in args.only:
                continue
            print(f"[{case['id']}] .Resi", flush=True)
            entry, rep = build_resi_case(case, case_no, reg, out_root, tmp, rng, originals)
            manifest["cases"].append(entry)
            reports[case["id"]] = rep
        n0 = len(M["resi_cases"])
        for i, tc in enumerate(M["trace_cases"], 1):
            if args.only and tc["id"] not in args.only:
                continue
            print(f"[{tc['id']}] trace {tc.get('stratum')}", flush=True)
            manifest["cases"].append(build_trace_case(tc, n0 + i, reg, db, out_root, tmp, rng, originals))

    M["maps"] = reg.maps
    M["structure_reports"] = {k: {"structure_mismatch": v["structure_mismatch"],
                                  "value_mismatch": v["value_mismatch"],
                                  "actions": v["actions"]} for k, v in reports.items()}
    map_path.write_text(json.dumps(M, indent=1, ensure_ascii=False))

    if args.only:
        print(json.dumps(manifest["cases"], indent=1, ensure_ascii=False))
        return
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    needles, hits = grep_outputs(out_root, originals, reg)
    manifest["checks"] = {
        "original_identifiers_searched": len(needles),
        "original_identifiers_found": len(hits),
    }
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    # hits contain original strings: report them only to the console / private map
    M["grep_hits"] = hits
    map_path.write_text(json.dumps(M, indent=1, ensure_ascii=False))
    size = sum(p.stat().st_size for p in out_root.rglob("*") if p.is_file())
    print(f"corpus: {len(manifest['cases'])} cases, {size / 1e6:.2f} MB; "
          f"{len(needles)} original identifiers searched, {len(hits)} found")
    for h in hits:
        print("  FOUND", h)
    problems = [c["id"] for c in manifest["cases"]
                if c.get("trace_check_problems") or c.get("unreviewed_strings")]
    if problems:
        print("cases with problems:", problems)
    return 1 if hits or problems else 0


if __name__ == "__main__":
    sys.exit(main())
