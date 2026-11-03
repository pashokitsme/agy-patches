#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import shutil
from struct import unpack_from
import sys
import tempfile

DEFAULT_TARGET = Path("/Applications/Antigravity.app/Contents/Resources/bin/language_server")


def branch_delta(instruction, shift, bits):
    value = (instruction >> shift) & ((1 << bits) - 1)
    if value & (1 << (bits - 1)):
        value -= 1 << bits
    return value << 2


def unconditional_branch(delta):
    if delta % 4 or not -(1 << 27) <= delta < (1 << 27):
        raise ValueError("Branch target is out of range")
    return 0x14000000 | ((delta >> 2) & 0x03FFFFFF)


def locate_patch(path):
    data = path.read_bytes()
    matches = []
    start = 0
    while True:
        high_byte = data.find(b"\x54", start)
        if high_byte < 0:
            break
        start = high_byte + 1
        site = high_byte - 3
        if site < 0 or site % 4 or site + 8 > len(data):
            continue
        allowed_check, rejection = unpack_from("<2I", data, site)
        if allowed_check & 0xFF00001F != 0x5400000C:
            continue
        success = site + 8
        if site + branch_delta(allowed_check, 5, 19) != success:
            continue
        patch_offset = site + 4
        replacement = unconditional_branch(success - patch_offset)
        if rejection & 0xFF00001F == 0xB5000000 and patch_offset + branch_delta(rejection, 5, 19) != success:
            state = "original"
        elif rejection & 0xFC000000 == 0x14000000 and patch_offset + branch_delta(rejection, 0, 26) == success:
            state = "patched"
        else:
            continue
        matches.append((state, patch_offset, rejection, replacement))
    if len(matches) != 1:
        offsets = ", ".join(hex(match[1]) for match in matches) or "none"
        raise ValueError(f"Expected one ineligible-tier branch, found {len(matches)}: {offsets}")
    return matches[0]


def get_state(path):
    if not path.is_file():
        raise ValueError(f"Target is not a file: {path}")
    return locate_patch(path)[0]


def apply_patch(path):
    state, offset, original, replacement = locate_patch(path)
    if state != "original":
        raise ValueError(f"Cannot patch target in state: {state}")
    original_bytes = original.to_bytes(4, "little")
    replacement_bytes = replacement.to_bytes(4, "little")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.patch-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(path, temporary)
        with temporary.open("r+b") as output:
            output.seek(offset)
            if output.read(4) != original_bytes:
                raise ValueError("Target changed while patching")
            output.seek(offset)
            output.write(replacement_bytes)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return offset, original_bytes, replacement_bytes


def main():
    parser = argparse.ArgumentParser(description="Patch Antigravity arm64 ineligible-tier rejection")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        state = get_state(args.target)
        print(f"{args.target}: {state}")
        if args.check or state == "patched":
            return 0
        offset, original, replacement = apply_patch(args.target)
        if get_state(args.target) != "patched":
            raise ValueError("Patch verification failed")
        print(f"Patched {offset:#x}: {original.hex()} -> {replacement.hex()}")
        return 0
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
