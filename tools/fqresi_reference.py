#!/usr/bin/env python
"""Build tests/data/fqresi_reference.json: FQResi's own density traces
(createCorrArray) for one corpus trace under a grid of settings, from two
FQResi versions: before the app 5.5 standardisation change (2a975eb) and
after it (c27a74b).

Usage:
    python tools/fqresi_reference.py [--fqresi ~/FQResi]

Needs R with jsonlite and a git checkout of FQResi. Every 25th sample is
kept to keep the file small.
"""
import argparse
import itertools
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
from imlresi import ResiResultSet  # noqa: E402

COMMITS = {"Version 5.0.0": "2a975eb", "Version 5.6.0": "c27a74b"}
FILES = ["TraceStandardise.R", "CreateCorrArray.R", "NonLinearBaselineCorrection.R"]
STEP = 25


def cases():
    for ver, baseline, res, rpm, eqn in itertools.product(
            COMMITS, ["Linear", "NonLinear"],
            ["RadiataPine", "Enitens", "Eglobulus", "HoopPine", "HighDensityHardwood", "Mystery"],
            [2500.0, 3500.0], ["Linear", "Ln"]):
        if ver == "Version 5.0.0" and baseline == "NonLinear":
            continue  # FQResi of June 2026 used the sigmoid; app 5.0 didn't (see C14)
        yield dict(Version=ver, Standardised=True, ResiCode="PD400-9000", FeedSpeed=2000.0, RPM=rpm,
                   Resource=res, DOB=380.4, TraceType="B-B", BaselineMethod=baseline, BLCorrDen=12.3,
                   BarkThickness=21.7, EqnType=eqn,
                   rSlope=9.238 if eqn == "Linear" else 304.0, rIntcpt=173.0 if eqn == "Linear" else -547.0,
                   UBDIA=330.15, EntryRadius=170.0, MOEmodel="")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fqresi", default=str(Path.home() / "FQResi"))
    args = ap.parse_args()
    drill = ResiResultSet(REPO / "tests/data/corpus/resi/C03/C03.Resi")[0].drill.astype(float).tolist()
    all_cases = list(cases())
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for ver, commit in COMMITS.items():
            src = tmp / commit
            src.mkdir()
            for f in FILES:
                (src / f).write_text(subprocess.run(["git", "-C", args.fqresi, "show", f"{commit}:R/{f}"],
                                                    check=True, capture_output=True, text=True).stdout)
            mine = [c for c in all_cases if c["Version"] == ver]
            (tmp / "inp.json").write_text(json.dumps([dict(drill=drill, sData=c) for c in mine]))
            subprocess.run(["Rscript", str(REPO / "tools/fqresi_reference.R"), str(tmp / "inp.json"),
                            str(tmp / "out.json"), commit], check=True, capture_output=True, cwd=tmp)
            for c, den in zip(mine, json.loads((tmp / "out.json").read_text())):
                out.append(dict(sData=c, fqresi_commit=commit, length=len(den), den_every_25=den[::STEP]))
    (REPO / "tests/data/fqresi_reference.json").write_text(json.dumps(
        {"source": "C03_01 drill trace; RPMCoef a=-0.786 b=1", "step": STEP, "cases": out}, indent=0))
    print(len(out), "cases")


if __name__ == "__main__":
    main()
