#!/usr/bin/env python3
import importlib.metadata
import re
import sys
from pathlib import Path

def parse(line):
    line=line.strip()
    if not line or line.startswith("#"): return None
    m=re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)(?:==([A-Za-z0-9_.+!-]+))?", line)
    if not m: raise ValueError(line)
    return m.group(1).replace("_","-").lower(),m.group(2)

def main():
    if len(sys.argv)!=2: return 2
    p=Path(sys.argv[1])
    if not p.is_file(): return 2
    try:
        for raw in p.read_text(encoding="utf-8").splitlines():
            req=parse(raw)
            if not req: continue
            name,wanted=req
            try: installed=importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError: return 1
            if wanted and installed != wanted: return 1
    except Exception: return 2
    return 0
if __name__=="__main__": raise SystemExit(main())
