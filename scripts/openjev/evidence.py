"""Retention of the Open-Jev v3 per-decision evidence (R3.2H): build / verify a checksum-verified archive.

The ~17 MB of per-decision JSON (audit/openjev-v3/{dev,cal,opt,final}/*.json) is NOT kept in the integrated Git history. Its identity is pinned
by audit/openjev-v3/evidence-manifest.json (sha256 + size of every member, sha256 of the archive, the Git blob id and source commit it came from),
and the original blobs stay reachable on branch feature/run3-openjev-optimization (commit in the manifest).

  uv run python scripts/openjev/evidence.py build  [--src-commit REV] [--out PATH]   # writes the archive + manifest (refuses to overwrite)
  uv run python scripts/openjev/evidence.py verify --archive PATH                     # archive bytes + every member vs the manifest
  uv run python scripts/openjev/evidence.py verify --dir audit/openjev-v3             # extracted tree vs the manifest
  uv run python scripts/openjev/evidence.py verify --git                              # blobs at the manifest's source commit vs the manifest
  uv run python scripts/openjev/evidence.py extract --archive PATH                    # verified extraction into audit/openjev-v3 (git-ignored dirs)

verify exits non-zero on ANY mismatch, missing or extra member.
"""
import argparse
import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "audit" / "openjev-v3"
MANIFEST = EV / "evidence-manifest.json"
PARTS = ("dev", "cal", "opt", "final")
DEFAULT_ARCHIVE = EV / "openjev-v3-evidence.tar.gz"          # committed: 0.7 MB deterministic archive of the 17.7 MB per-decision JSON


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def members_from_dir(base: Path) -> dict[str, bytes]:
    out = {}
    for part in PARTS:
        for f in sorted((base / part).glob("*.json")):
            out[f"{part}/{f.name}"] = f.read_bytes()
    return out


def git(*a) -> bytes:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, check=True).stdout


def make_archive(members: dict[str, bytes]) -> bytes:
    """Deterministic tar.gz: sorted names, zeroed mtime/owner, gzip mtime 0 (same input -> same bytes)."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for name in sorted(members):
            ti = tarfile.TarInfo(f"openjev-v3/{name}")
            ti.size, ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname, ti.mode = len(members[name]), 0, 0, 0, "", "", 0o644
            tf.addfile(ti, io.BytesIO(members[name]))
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(raw.getvalue())
    return buf.getvalue()


def members_from_archive(blob: bytes) -> dict[str, bytes]:
    out = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for ti in tf.getmembers():
            if not ti.isfile():
                raise SystemExit(f"unexpected non-file member {ti.name!r}")
            name = ti.name.removeprefix("openjev-v3/")
            if name.startswith(("/", "..")) or ".." in Path(name).parts or ti.name == name:
                raise SystemExit(f"unsafe member path {ti.name!r}")
            out[name] = tf.extractfile(ti).read()
    return out


def check(members: dict[str, bytes], man: dict) -> list[str]:
    want, errs = man["members"], []
    for name in sorted(set(want) | set(members)):
        if name not in members:
            errs.append(f"MISSING {name}")
        elif name not in want:
            errs.append(f"EXTRA {name}")
        else:
            b = members[name]
            if sha(b) != want[name]["sha256"] or len(b) != want[name]["bytes"]:
                errs.append(f"MISMATCH {name}")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "verify", "extract"])
    ap.add_argument("--archive")
    ap.add_argument("--dir")
    ap.add_argument("--git", action="store_true")
    ap.add_argument("--src-commit", default="origin/feature/run3-openjev-optimization")
    ap.add_argument("--out")
    a = ap.parse_args()

    if a.cmd == "build":
        out = Path(a.out) if a.out else DEFAULT_ARCHIVE
        if out.exists() or MANIFEST.exists():
            raise SystemExit("refusing to overwrite an existing archive/manifest")
        commit = git("rev-parse", a.src_commit).decode().strip()
        members, blobs = {}, {}
        for line in git("ls-tree", "-r", commit, "--", "audit/openjev-v3").decode().splitlines():
            meta, path = line.split("\t")
            rel = path.removeprefix("audit/openjev-v3/")
            if rel.split("/")[0] in PARTS and "/" in rel:
                members[rel] = git("cat-file", "blob", meta.split()[2])
                blobs[rel] = meta.split()[2]
        if not members:
            raise SystemExit("no per-decision members found at the source commit")
        if members != members_from_dir(EV):
            raise SystemExit("working-tree copies differ from the source commit: refusing to archive unverified data")
        blob = make_archive(members)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(blob)
        man = {"note": "Checksums of the Open-Jev v3 per-decision evidence kept OUT of the integrated Git history. Historical, immutable "
                       "research data; verify with scripts/openjev/evidence.py. See audit/openjev-v3/EVIDENCE-RETENTION.md.",
               "source_commit": commit, "archive": {"name": out.name, "sha256": sha(blob), "bytes": len(blob)},
               "total_member_bytes": sum(len(b) for b in members.values()),
               "members": {n: {"sha256": sha(b), "bytes": len(b), "git_blob": blobs[n]} for n, b in sorted(members.items())}}
        MANIFEST.write_text(json.dumps(man, indent=1) + "\n")
        print(f"archive {out} {len(blob)} bytes sha256 {sha(blob)}; {len(members)} members; manifest {MANIFEST}")
        return 0

    man = json.loads(MANIFEST.read_text())
    if a.cmd == "verify":
        if a.archive:
            blob = Path(a.archive).read_bytes()
            errs = [] if sha(blob) == man["archive"]["sha256"] else ["ARCHIVE sha256 mismatch"]
            errs += check(members_from_archive(blob), man)
        elif a.dir:
            errs = check(members_from_dir(Path(a.dir)), man)
        elif a.git:
            members = {}
            for line in git("ls-tree", "-r", man["source_commit"], "--", "audit/openjev-v3").decode().splitlines():
                meta, path = line.split("\t")
                rel = path.removeprefix("audit/openjev-v3/")
                if rel.split("/")[0] in PARTS and "/" in rel:
                    members[rel] = git("cat-file", "blob", meta.split()[2])
            errs = check(members, man)
        else:
            raise SystemExit("verify needs --archive, --dir or --git")
        print("\n".join(errs) or f"OK: {len(man['members'])} members match the manifest")
        return 1 if errs else 0

    if a.cmd == "extract":
        if not a.archive:
            raise SystemExit("extract needs --archive")
        blob = Path(a.archive).read_bytes()
        members = members_from_archive(blob)
        errs = ([] if sha(blob) == man["archive"]["sha256"] else ["ARCHIVE sha256 mismatch"]) + check(members, man)
        if errs:
            print("\n".join(errs))
            return 1
        for name, b in members.items():
            dest = EV / name
            if dest.exists() and dest.read_bytes() != b:
                raise SystemExit(f"refusing to overwrite differing {dest}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b)
        print(f"extracted {len(members)} verified members into {EV}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
