"""Frontend-only checkpoints. Never include environment files or databases."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "output" / "ui-versions"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create(label: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = STORE / f"{stamp}-{label}"
    destination.mkdir(parents=True, exist_ok=False)
    sources = sorted(p for folder in ("app", "tests") for p in (ROOT / folder).rglob("*")
                     if p.is_file() and not p.name.startswith(".env") and p.suffix not in {".db", ".sqlite", ".sqlite3", ".pem"})
    sources += [ROOT / name for name in ("package.json", "README.md") if (ROOT / name).exists()]
    files = []
    for source in sources:
        relative = source.relative_to(ROOT)
        target = destination / "files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        files.append({"path": relative.as_posix(), "sha256": digest(source)})
    manifest = {"version": 1, "created_at_local": datetime.now().isoformat(), "scope": "frontend-only", "files": files}
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Snapshot: {destination}\nFiles: {len(files)}")
    return destination


def restore(snapshot: str, apply: bool) -> None:
    source = Path(snapshot).resolve()
    if not source.is_relative_to(STORE.resolve()):
        raise SystemExit("Only project-local output/ui-versions snapshots can be restored.")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    pairs = []
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        target = (ROOT / relative).resolve()
        original = (source / "files" / relative).resolve()
        allowed = relative.parts[0] in {"app", "tests"} or relative.as_posix() in {"package.json", "README.md"}
        if not allowed or not target.is_relative_to(ROOT.resolve()) or not original.is_relative_to((source / "files").resolve()):
            raise SystemExit("Unsafe snapshot path.")
        if digest(original) != entry["sha256"]:
            raise SystemExit(f"Snapshot checksum mismatch: {relative}")
        if not target.exists() or digest(target) != entry["sha256"]:
            pairs.append((original, target))
    print(f"Restore preview: {len(pairs)} changed files. Backend, data, environment and dependencies are excluded.")
    if not apply:
        print("No files changed. Add --apply to restore; current frontend will be checkpointed first.")
        return
    create("before-restore")
    for original, target in pairs:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
    print("Frontend restored. Newly added, unreferenced files are retained. Restart/rebuild the frontend if needed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "restore"])
    parser.add_argument("--label", default="manual", choices=["manual", "before-redesign", "after-redesign"])
    parser.add_argument("--snapshot")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.action == "create":
        create(args.label)
    elif not args.snapshot:
        parser.error("restore requires --snapshot")
    else:
        restore(args.snapshot, args.apply)
