"""Archive public anchor-source files without guessing workbook layouts."""

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4
import zipfile


def fetch_official_inputs(config_path, output, opener=urlopen):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    sources = config["sources"]
    if len({s["key"] for s in sources}) != len(sources):
        raise ValueError("Official source keys must be unique.")
    if len({s["filename"] for s in sources}) != len(sources):
        raise ValueError("Official filenames must be unique.")
    for source in sources:
        if Path(source["filename"]).name != source["filename"] or source["filename"] in {".", ".."}:
            raise ValueError("Official filenames must be plain filenames.")
        if urlparse(source["url"]).scheme != "https":
            raise ValueError("Official downloads must use HTTPS.")
        if source["format"] not in {"xlsx", "xls", "csv"}:
            raise ValueError("Unsupported official file format.")
    stamp = datetime.now(timezone.utc)
    folder = Path(output) / (stamp.strftime("%Y%m%dT%H%M%S") + "_official_" + uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    results = []
    for source in sources:
        record = dict(source)
        try:
            request = Request(source["url"], headers={"User-Agent": "CMA-input-research/0.1"})
            with opener(request, timeout=20) as response:
                payload = response.read()
                record["resolved_url"] = response.geturl()
            if not payload:
                raise ValueError("Empty download.")
            if source["format"] == "xlsx":
                with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                    if "xl/workbook.xml" not in archive.namelist():
                        raise ValueError("Response is not an Excel workbook.")
            elif source["format"] == "xls":
                if not payload.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
                    raise ValueError("Response is not an XLS compound file.")
            else:
                first_line = payload.decode("utf-8-sig").splitlines()[0]
                if "," not in first_line or "<html" in first_line.lower() or "<!doctype" in first_line.lower():
                    raise ValueError("Response is not a recognized CSV.")
            (folder / source["filename"]).write_bytes(payload)
            record.update(status="ok", bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            record.update(status="error", error=str(exc))
        results.append(record)
    manifest = {"retrieved_at_utc": stamp.isoformat(), "kind": "official_anchor_sources",
                "note": "Download time does not establish historical release availability. Preserve original files and map their vintage/release definitions before backtesting.",
                "sources": results}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return folder, results
