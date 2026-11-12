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

## Verified baseline results

The complete Release build passed in Ubuntu 24.04.3 userspace with GCC 13.3.0,
Qt 6.8.3, CMake 3.31.6 and Ninja 1.13.2. All emulator C++ sources remained at
the pinned upstream revision. The rootless cloud host was Debian 13 on an
AMD EPYC 9V74, with 9.7 GiB RAM and no hardware GPU device.

| Check | Result |
| --- | --- |
| GUI and CLI | `lichii` and `eden-cli` linked successfully |
| CTest | 9/9 suites passed in 45.87 seconds |
| Permission cases skipped under UID 0 | All 3 passed separately as UID 1000 using the Ubuntu dynamic loader |
| Remaining coverage gap | 4 LDN cases skipped: no host IPv4 interface |
| Python helper suites | 54 tests passed |
| GCC 13 switch discovery | 5 tests passed |
| Compiled ThreadWorker controls | Cancellation and completion both woke |
| CLI `--help`, `--version` | Exit 0 |
| Missing game path | SIGSEGV, exit 139 after loader failure |
| Original ExeFS | Guest marker and `ExitProcess` reached; no natural exit |
| Corrupt META control | Incorrectly executed the same guest; no natural exit |

The CTest run dropped Linux capabilities. Its main suite passed 1,224 cases
with 5 skips; the separate UID-1000 run covered the skipped NUP permission case.
The two other UID-0 skips were updater rollback cases, also covered separately.
Hosted CI has not run on this fork.

Default automatic audio selection aborted in cubeb's ALSA initialization in
this cloud environment. The CPU/loader trials used the supported null backend:

```ini
[Audio]
output_engine\default=false
output_engine=3
```

With SDL dummy video/audio and isolated HOME/XDG directories, both the valid
and malformed fixtures printed the guest marker and logged `ExitProcess`.
Neither exited after 15 seconds; timeout sent TERM, then KILL four seconds later
(exit 137). These runs establish CPU execution and two failing loader/lifecycle
controls, not graphics or audio correctness.

Baseline binary SHA-256:

- `lichii`: `13e998213fb5113440ba9b5c91e9bdabaa666afa180f226dad6eb467ec7991eb`
- `eden-cli`: `d48270b19cb28bd9761cdd79797b20216f8274b7a81d88e640e6557c339ca9fe`

## First runtime task: reject malformed metadata before execution

`ProgramMetadata::Load` in `src/core/file_sys/program_metadata.cpp` reads the
NPDM header without checking its `META` magic. The corrupt control changes only
those four bytes, yet the pinned runtime still executes its NSO. Fix this before
expanding compatibility claims or importing additional workloads.

Add the header check before interpreting its offsets, preserving both legacy
and extended ACID layouts. Reuse the existing original fixture below for a
small parser regression and the CLI negative control. Require
`ErrorBadNPDMHeader`, no guest marker, and a clean nonzero CLI exit. Missing and
truncated inputs must remain rejected. The existing missing-path SIGSEGV means
cold-load teardown also needs qualification before that CLI acceptance gate
can pass. [Eglantine #198](https://github.com/Eglantine-Community/Eglantine/pull/198)
has a related early-return workaround; review its state-lifetime implications
before porting it.

## Next lifecycle task: terminate the guest and frontend

At the pinned revision, `ExitProcess` in
`src/core/hle/kernel/svc/svc_process.cpp` calls `System::Exit` without terminating
the current process. `SDL_AppInit` in `src/yuzu_cmd/yuzu.cpp` registers an empty
exit callback, and `SDL_AppIterate` checks only restart state and the SDL window.
The original guest reproduces the failure: it reaches `ExitProcess` but both
guest and frontend remain alive until forced termination.

Reuse NX2 Lab's `tools/reference/eden_ns2/make_native_exefs.py` at
`68ac0e5e444a1ec490154fa0de00d42fdf35610c`. It creates an original ARM64 program
that prints a marker and calls `ExitProcess`; it needs no firmware or keys.

| Input | SHA-256 |
| --- | --- |
| `main` | `508edcf6870546ed2f67c6ed11f0df3deb0242427ea2b9d7562ae6d015084ed5` |
| `main.npdm` | `64e25a2e3e37495d75341f9564afa3e6a665f10f94b36ea7e4e3c533b4573148` |
| Corrupt `main.npdm` (`META` → `NX2!`) | `4434c4802b89b9452a05d36ae1ad83e386034ddb55618e0651de52ee2866e6d8` |

Run the untouched baseline first with isolated HOME/XDG directories,
`SDL_VIDEODRIVER=dummy`, `SDL_AUDIODRIVER=dummy`,
`eden-cli --null-render --singlecore --game /path/to/guest/main`, and a bounded
timeout. Require the guest marker and natural exit code zero. A timeout after
the marker confirms the frontend lifecycle failure; a loader failure does not.
Keep the malformed-META negative control strict.

Check current Lichii/Eglantine fixes before changing code. Reuse
the earlier lab experiment in `tools/reference/eden_ns2/overlay_eden_exit.py`
at the same lab revision: process termination plus a thread-safe exit request
consumed by the SDL thread. Adapt it to the current source and preserve its
GPL-3.0-only notice and source attribution; its guards target the older Eden build.
Do not tear down the system from the guest callback. Verify natural guest exit,
window close, failed initialization, `--help`, `--version`, and ExecuteProgram's
restart code 75. Then run the existing multi-frame graphics workload, followed
by original input/audio/filesystem coverage. Full multisystem homebrew execution
is the next milestone; a successful build alone does not establish it.
