"""Small helpers shared by the pipeline scripts."""
import hashlib
import zipfile
from datetime import datetime, timezone

import pandas as pd

import config


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def log_provenance(name: str, source: str, path, note: str = ""):
    """Record where a raw input came from and when it was pulled (one row per input)."""
    row = {
        "input": name,
        "source": source,
        "local_path": str(path.relative_to(config.DATA.parent)) if str(path).startswith(str(config.DATA.parent)) else str(path),
        "pulled_at_utc": utc_now(),
        "bytes": path.stat().st_size if path.exists() else None,
        "sha256": sha256(path) if path.exists() and path.is_file() else None,
        "note": note,
    }
    if config.PROVENANCE_FILE.exists():
        prov = pd.read_csv(config.PROVENANCE_FILE)
        prov = prov[prov["input"] != name]
        prov = pd.concat([prov, pd.DataFrame([row])], ignore_index=True)
    else:
        prov = pd.DataFrame([row])
    prov.sort_values("input").to_csv(config.PROVENANCE_FILE, index=False)


def zip_member(zf: zipfile.ZipFile, table: str) -> str:
    """Find e.g. 'INFOTABLE.tsv' inside an SEC zip, whatever folder it sits in."""
    for n in zf.namelist():
        if n.split("/")[-1].upper() == f"{table.upper()}.TSV":
            return n
    raise FileNotFoundError(f"{table}.tsv not found in {zf.filename}")


def parse_sec_date(s: pd.Series) -> pd.Series:
    """SEC 13F dates look like 31-DEC-2023."""
    return pd.to_datetime(s.str.strip().str.title(), format="%d-%b-%Y", errors="coerce")


def yf_ticker(figi_ticker: str) -> str:
    """OpenFIGI writes share classes as BRK/B; Yahoo wants BRK-B."""
    return figi_ticker.strip().upper().replace("/", "-").replace(" ", "-")


def qstr(q) -> str:
    return str(pd.Period(q, freq="Q"))
