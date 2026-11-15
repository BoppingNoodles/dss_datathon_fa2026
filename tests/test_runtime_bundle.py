import io
import json
import tarfile

import pytest

from src.data.runtime_bundle import FILES, MANIFEST, create, install


def bundle_fixture(root):
    directory = root / "data/processed/real"
    directory.mkdir(parents=True)
    for name in FILES:
        (directory / name).write_text("example " + name)
    (directory / "person1_coverage.json").write_text(json.dumps({"data_mode": "full", "retained": {"jobs": 3}}))


def test_roundtrip_preserves_unrelated_files(tmp_path):
    producer = tmp_path / "producer"
    bundle_fixture(producer)
    archive = tmp_path / "runtime.tar.gz"
    result = create(archive, producer)
    assert result["retained"]["jobs"] == 3
    assert archive.with_name(archive.name + ".sha256").is_file()
    consumer = tmp_path / "consumer"
    directory = consumer / "data/processed/real"
    directory.mkdir(parents=True)
    (directory / "keep.txt").write_text("preserve")
    install(archive, consumer)
    for name in FILES:
        assert (directory / name).read_bytes() == (producer / "data/processed/real" / name).read_bytes()
    assert (directory / "keep.txt").read_text() == "preserve"


@pytest.mark.parametrize("bad", ["checksum", "traversal", "link", "duplicate"])
def test_invalid_archive_never_replaces_existing_data(tmp_path, bad):
    producer = tmp_path / "producer"
    bundle_fixture(producer)
    original = tmp_path / "runtime.tar.gz"
    create(original, producer)
    corrupt = tmp_path / "bad.tar.gz"
    with tarfile.open(original) as incoming, tarfile.open(corrupt, "w:gz") as outgoing:
        for member in incoming.getmembers():
            payload = incoming.extractfile(member).read()
            if member.name == "jobs.jsonl":
                if bad == "checksum":
                    payload = b"!" * len(payload)
                elif bad == "traversal":
                    member.name = "../jobs.jsonl"
                elif bad == "link":
                    member.type = tarfile.SYMTYPE
                    member.linkname = "/tmp/jobs.jsonl"
                    member.size = 0
            outgoing.addfile(member, io.BytesIO(payload))
            if bad == "duplicate" and member.name == MANIFEST:
                outgoing.addfile(member, io.BytesIO(payload))
    consumer = tmp_path / "consumer"
    bundle_fixture(consumer)
    target = consumer / "data/processed/real/jobs.jsonl"
    target.write_text("original")
    with pytest.raises(ValueError):
        install(corrupt, consumer)
    assert target.read_text() == "original"
