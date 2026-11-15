"""Create/install a small, checksummed real-data runtime handoff, without raw inputs.

    uv run python -m src.data.runtime_bundle create
    uv run python -m src.data.runtime_bundle install /path/to/phoenix-real-runtime-v1.tar.gz
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile

from src.common import ROOT, sha256_file

FILES = ("jobs.jsonl", "rentals.jsonl", "person1_coverage.json",
         "service_candidates.parquet", "area_reference_points.parquet",
         "places_stats.json", "reviews_stats.json", "index_stats.json")
DEFAULT_BUNDLE = ROOT / "data/processed/phoenix-real-runtime-v1.tar.gz"
MANIFEST = "runtime_manifest.json"


def create(output: Path, root: Path = ROOT) -> dict:
    directory = root / "data/processed/real"
    missing = [name for name in FILES if not (directory / name).is_file()]
    if missing:
        raise ValueError(f"Incomplete real runtime: {', '.join(missing)}")
    coverage = json.loads((directory / "person1_coverage.json").read_text())
    if coverage.get("data_mode") != "full":
        raise ValueError("Refusing to label non-full data as real")
    manifest = {"format": "phoenix-real-runtime-v1", "source": "real",
                "retained": coverage.get("retained", {}),
                "files": {name: {"bytes": (directory / name).stat().st_size,
                                  "sha256": sha256_file(directory / name)} for name in FILES}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz", compresslevel=6) as archive:
        for name in FILES:
            archive.add(directory / name, arcname=name, recursive=False)
        payload = (json.dumps(manifest, indent=2) + "\n").encode()
        info = tarfile.TarInfo(MANIFEST)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    checksum = sha256_file(output)
    output.with_name(output.name + ".sha256").write_text(f"{checksum}  {output.name}\n")
    return {"bundle": str(output), "bytes": output.stat().st_size, "sha256": checksum, **manifest}


def install(bundle: Path, root: Path = ROOT) -> dict:
    """Validate every member before replacing only runtime files; preserve other data."""
    directory = root / "data/processed/real"
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".runtime-", dir=directory.parent) as temporary:
        staging = Path(temporary)
        with tarfile.open(bundle, "r:gz") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if len(names) != len(set(names)) or set(names) != {*FILES, MANIFEST}:
                raise ValueError("Bundle must contain exactly the Phoenix runtime files and manifest")
            if any(not member.isfile() for member in members):
                raise ValueError("Bundle links and directories are not allowed")
            # Bound decompression and the manifest before reading untrusted bytes.
            if sum(m.size for m in members) > 2_000_000_000 or archive.getmember(MANIFEST).size > 100_000:
                raise ValueError("Runtime bundle exceeds supported size")
            manifest = json.load(archive.extractfile(MANIFEST))
            if manifest.get("format") != "phoenix-real-runtime-v1" or manifest.get("source") != "real":
                raise ValueError("Unsupported runtime manifest")
            if set(manifest.get("files", {})) != set(FILES):
                raise ValueError("Manifest file list does not match the runtime")
            for name in FILES:
                expected = manifest["files"][name]
                member = archive.getmember(name)
                if member.size != expected["bytes"]:
                    raise ValueError(f"Size mismatch: {name}")
                digest = hashlib.sha256()
                with archive.extractfile(member) as incoming, (staging / name).open("wb") as outgoing:
                    while block := incoming.read(1 << 20):
                        digest.update(block)
                        outgoing.write(block)
                if digest.hexdigest() != expected["sha256"]:
                    raise ValueError(f"Checksum mismatch: {name}")
        coverage = json.loads((staging / "person1_coverage.json").read_text())
        if coverage.get("data_mode") != "full":
            raise ValueError("Real runtime requires a full coverage manifest")
        directory.mkdir(parents=True, exist_ok=True)
        for name in FILES:
            os.replace(staging / name, directory / name)
        (directory / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    return {"installed": str(directory), "retained": manifest.get("retained", {}),
            "next": "Restart with make api SOURCE=real; GET http://localhost:8000/health"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("create")
    export.add_argument("--output", type=Path, default=DEFAULT_BUNDLE)
    unpack = commands.add_parser("install")
    unpack.add_argument("bundle", type=Path)
    args = parser.parse_args()
    result = create(args.output) if args.command == "create" else install(args.bundle)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
