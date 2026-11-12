<!-- SPDX-FileCopyrightText: 2026 Astraea NX2 contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Runtime bootstrap

NX2's runtime lives in [astraea-emu/nx2](https://github.com/astraea-emu/nx2),
a GitHub fork of [Lichii](https://github.com/zortos293/Lichii).
The separate [NX2 Lab](https://github.com/astraea-emu/nx2-lab/issues/50)
provides original guest workloads and conformance tools.

Baseline: `build-160`, commit `2eb5f081c8734affd272466f89133aa4e3e56e18`.
The fork retains upstream history, notices and licenses. The default `nx2`
branch remains the upstream baseline; bootstrap work is on `bootstrap/build-160`.
This bootstrap changes build tooling, not emulation behavior or branding.

## Reproduce the Linux build

Use Ubuntu 24.04, GCC/G++ 13, Ninja, CMake 3.31 or newer, and Qt 6.8.3
(including Qt Charts and Linguist tools). Install the Linux dependencies listed
in the pinned [build-check workflow](../../.github/workflows/build-check.yml).
The preset uses that workflow's production GUI, CLI and test options.

```sh
export QT_ROOT_DIR=/path/to/Qt/6.8.3/gcc_64
cmake --preset linux-gcc13
cmake --build --preset linux-gcc13
ctest --preset linux-gcc13
python3 tools/nx2/test_debug_mcp.py
python3 tools/nx2/test_cache_metrics.py
python3 tools/nx2/test_cache_bench.py
python3 tools/nx2/test_thread_worker_wake.py
python3 -I tools/nx2/thread_worker_wake.py --cxx g++-13
CXX=g++-13 python3 tools/nx2/test_switches.py
```

The preset defaults to three build jobs; override with `--parallel` for the
available RAM. Expected production artifacts are `build/bin/lichii` (GUI) and
`build/bin/eden-cli` (CLI). Retain the source SHA, CMake cache, dependency
versions and complete test output alongside each local build.

## First runtime task: guest exit in the CLI

At the pinned revision, `SDL_AppInit` in `src/yuzu_cmd/yuzu.cpp` registers an
empty exit callback. `WindowSystem::PruneTerminatedAppletsLocked` calls `System::Exit`
when the last applet terminates, but `SDL_AppIterate` checks only restart state
and the SDL window. Investigate whether a guest that exits leaves the CLI alive.
This is a source finding awaiting an executable reproduction.

Reuse NX2 Lab's `tools/reference/eden_ns2/make_native_exefs.py` at
`68ac0e5e444a1ec490154fa0de00d42fdf35610c`. It creates an original ARM64 program
that prints a marker and calls `ExitProcess`; it needs no firmware or keys.

| Input | SHA-256 |
| --- | --- |
| `main` | `508edcf6870546ed2f67c6ed11f0df3deb0242427ea2b9d7562ae6d015084ed5` |
| `main.npdm` | `64e25a2e3e37495d75341f9564afa3e6a665f10f94b36ea7e4e3c533b4573148` |

Run the untouched baseline first with isolated HOME/XDG directories,
`SDL_VIDEODRIVER=dummy`, `SDL_AUDIODRIVER=dummy`,
`eden-cli --null-render --singlecore --game /path/to/guest/main`, and a bounded
timeout. Require the guest marker and natural exit code zero. A timeout after
the marker confirms the frontend lifecycle failure; a loader failure does not.
Keep the malformed-META negative control strict.

If reproduced, check current Lichii/Eglantine fixes before changing code. The
smallest candidate is a thread-safe exit request consumed by the SDL thread;
do not tear down the system from the guest callback. Verify natural guest exit,
window close, failed initialization, `--help`, `--version`, and ExecuteProgram's
restart code 75. Then run the existing multi-frame graphics workload, followed
by original input/audio/filesystem coverage. Full multisystem homebrew execution
is the next milestone; a successful build alone does not establish it.
