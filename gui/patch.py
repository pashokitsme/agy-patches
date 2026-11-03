#!/usr/bin/env python3
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile

DEFAULT_TARGET = Path("/Applications/Antigravity.app/Contents/Resources/bin/language_server")
ORIGINAL_SHA256 = "8b660ea42c9e24b7a6be339bfa573d25b19d0770dba6e5185c205f2ad1da26d6"
PATCHED_SHA256 = "bf3569b5b83310bb7a64dceed17c6bbd5cbef916ad81a0fdd4042c7afc2e248d"
OFFSET = 0x237AA30
ORIGINAL = bytes.fromhex("200700b5")
PATCHED = bytes.fromhex("01000014")


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
        raise ValueError(f"Unsupported language_server: bytes at {OFFSET:#x} are {actual.hex()}")
    digest = file_sha256(path)
    if digest not in (ORIGINAL_SHA256, PATCHED_SHA256):
        raise ValueError(f"Unsupported language_server SHA-256: {digest}")
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
    parser = argparse.ArgumentParser(description="Patch Antigravity 2.28.2 arm64 ineligible-tier rejection")
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
