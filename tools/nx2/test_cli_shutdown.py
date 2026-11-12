#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Astraea NX2 contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded POSIX CLI shutdown regression using NX2 Lab's original ARM64 ExeFS.

Generate the input with tools/reference/eden_ns2/make_native_exefs.py from
astraea-emu/nx2-lab@68ac0e5e444a1ec490154fa0de00d42fdf35610c (GPL-3.0-only).
No keys, firmware or commercial guest are needed. Raw logs stay in --output-dir.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import time


def run_case(binary, guest, output, multicore, close):
    home = output / "home"
    config = home / "config/lichii"
    config.mkdir(parents=True)
    (config / "sdl2-config.ini").write_text(
        "[Audio]\noutput_engine\\default=false\noutput_engine=3\n")
    env = os.environ.copy()
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / "config"),
               XDG_DATA_HOME=str(home / "data"), XDG_CACHE_HOME=str(home / "cache"),
               SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    command = [str(binary), "--null-render"]
    if not multicore:
        command.append("--singlecore")
    command += ["--game", str(guest)]
    timed_out = False
    signal_sent = False
    started = time.monotonic()
    with (output / "console.log").open("wb") as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            if close:
                # Give the guest time to run; require its marker after shutdown as well.
                time.sleep(2)
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    signal_sent = True
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    engine_log = home / "data/lichii/log/eden_log.txt"
    data = (output / "console.log").read_bytes()
    if engine_log.exists():
        data += engine_log.read_bytes()
    marker = b"NX2 original extended ExeFS guest reached debug SVC" in data
    exited = b"ExitProcess: Process" in data
    quit_received = b"Quit requested" in data
    passed = (process.returncode == 0 and not timed_out and marker and
              (signal_sent and quit_received and not exited if close else exited))
    return dict(passed=passed, returncode=process.returncode, timed_out=timed_out,
                guest_executed=marker, exit_process_reached=exited,
                quit_received=quit_received, seconds=round(time.monotonic() - started, 3))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emulator", type=Path, required=True)
    parser.add_argument("--guest", type=Path, required=True, help="Original ExeFS main")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "posix":
        parser.error("This regression requires POSIX process-group signals")
    binary, guest, output = (p.resolve() for p in
                             (args.emulator, args.guest, args.output_dir))
    original = guest.read_bytes()
    npdm = guest.with_name("main.npdm").read_bytes()
    if (hashlib.sha256(original).hexdigest() !=
            "508edcf6870546ed2f67c6ed11f0df3deb0242427ea2b9d7562ae6d015084ed5" or
            hashlib.sha256(npdm).hexdigest() !=
            "64e25a2e3e37495d75341f9564afa3e6a665f10f94b36ea7e4e3c533b4573148"):
        parser.error("Expected the unchanged original ARM64 ExeFS fixture")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    live = output / "live"
    live.mkdir()
    nso = bytearray(original)
    # Replace ExitProcess with NOP; the next instruction loops indefinitely.
    struct.pack_into("<I", nso, 0x114, 0xD503201F)
    nso[0xA0:0xC0] = hashlib.sha256(nso[0x100:0x1100]).digest()
    (live / "main").write_bytes(nso)
    (live / "main.npdm").write_bytes(npdm)
    results = {}
    for multicore in (False, True):
        for close in (True, False):
            name = f"{'multicore' if multicore else 'singlecore'}-{'quit' if close else 'exit'}"
            results[name] = run_case(binary, live / "main" if close else guest,
                                     output / name, multicore, close)
            print(json.dumps({name: results[name]}), flush=True)
            (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    return 0 if all(r["passed"] for r in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
