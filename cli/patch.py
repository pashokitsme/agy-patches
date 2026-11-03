#!/usr/bin/env python3
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile

DEFAULT_TARGET = Path.home() / ".local/bin/agy"
ORIGINAL_SHA256 = "34423fc9b0af3841e7646aa72a2d40ffeab8218b22d1cb99eac7355f9eba31e3"
PATCHED_SHA256 = "bd0f26018c0eb608e00c83f42bcce8ed6c999829bdc24384bf914adb821c92ed"
OFFSET = 0x277EE6C
ORIGINAL = bytes.fromhex("420c0037")
PATCHED = bytes.fromhex("62000014")


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_bytes(path):
    with path.open("rb") as source:
        source.seek(OFFSET)
        return source.read(len(ORIGINAL))


def get_state(path):
    if not path.is_file():
        raise ValueError(f"Target is not a file: {path}")
    actual = current_bytes(path)
    if actual == PATCHED:
        return "patched"
    if actual != ORIGINAL:
        raise ValueError(f"Unsupported agy: bytes at {OFFSET:#x} are {actual.hex()}")
    digest = file_sha256(path)
    if digest not in (ORIGINAL_SHA256, PATCHED_SHA256):
        raise ValueError(f"Unsupported agy SHA-256: {digest}")
    return "original"


def apply_patch(path):
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.patch-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(path, temporary)
        with temporary.open("r+b") as output:
            output.seek(OFFSET)
            if output.read(len(ORIGINAL)) != ORIGINAL:
                raise ValueError("Target changed while patching")
            output.seek(OFFSET)
            output.write(PATCHED)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Patch agy 1.4.12 arm64 local eligibility rejection")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        state = get_state(args.target)
        print(f"{args.target}: {state}")
        if args.check or state == "patched":
            return 0
        apply_patch(args.target)
        if current_bytes(args.target) != PATCHED:
            raise ValueError("Patch verification failed")
        print(f"Patched {OFFSET:#x}: {ORIGINAL.hex()} -> {PATCHED.hex()}")
        print(f"Unsigned patched SHA-256: {file_sha256(args.target)}")
        return 0
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
