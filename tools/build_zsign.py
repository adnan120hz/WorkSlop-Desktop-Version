#!/usr/bin/env python3
"""Build zsign from source for the current platform.

zsign (https://github.com/zhlynn/zsign, MIT) signs the IPA with the user's
Apple development certificate. We build it from source in CI / on demand
rather than shipping an opaque binary.

Output: <repo>/vendor/zsign[.exe]  (git-ignored)

Requirements per platform:
- Linux: gcc, make, libssl-dev, zlib1g-dev
- macOS: Xcode CLT, openssl via brew (brew install openssl)
- Windows: MSYS2 with mingw-w64 toolchain (run inside MSYS2 shell)
"""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
VENDOR = REPO / "vendor"
ZSIGN_REPO = "https://github.com/zhlynn/zsign.git"


def run(cmd, cwd=None, env=None):
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def main():
    system = platform.system()
    VENDOR.mkdir(parents=True, exist_ok=True)
    work = HERE / ".zsign-build"
    if work.exists():
        shutil.rmtree(work)
    run(["git", "clone", "--depth", "1", ZSIGN_REPO, str(work)])

    if system == "Windows":
        # VS2022 solution in the repo; for CI we use MSYS2/MinGW make if
        # available, else the caller must build via Visual Studio.
        build_dir = work / "build" / "windows"
        # Fall back: try a MinGW make in build/windows if a Makefile exists.
        makefiles = list(build_dir.glob("Makefile")) + list(build_dir.glob("*.mk"))
        if not makefiles:
            raise SystemExit(
                "Windows zsign needs Visual Studio 2022: open "
                "build/windows/vs2022/zsign.sln and build, then copy "
                "zsign.exe to vendor/ manually.")
        run(["make"], cwd=build_dir)
        out = VENDOR / "zsign.exe"
    elif system == "Darwin":
        build_dir = work / "build" / "macos"
        # Prefer Homebrew OpenSSL; fall back to system search paths.
        env = os.environ.copy()
        for prefix in ("/opt/homebrew/opt/openssl", "/usr/local/opt/openssl"):
            inc = os.path.join(prefix, "include")
            lib = os.path.join(prefix, "lib")
            if os.path.isdir(inc):
                env["CXXFLAGS"] = env.get("CXXFLAGS", "") + f" -I{inc}"
                env["LDFLAGS"] = env.get("LDFLAGS", "") + f" -L{lib}"
                break
        run(["make"], cwd=build_dir, env=env)
        out = VENDOR / "zsign"
    else:
        build_dir = work / "build" / "linux"
        run(["make"], cwd=build_dir)
        out = VENDOR / "zsign"

    # Find the produced binary (the Makefiles drop it in <work>/bin/).
    candidates = [p for p in work.rglob("zsign")
                  if p.is_file() and os.access(p, os.X_OK)]
    # Also accept zsign.exe on Windows (not executable-bit on some FS).
    if system == "Windows" and not candidates:
        candidates = [p for p in work.rglob("zsign.exe") if p.is_file()]
    if not candidates:
        raise SystemExit("zsign build produced no binary")
    src = candidates[0]
    shutil.copy2(src, out)
    if system != "Windows":
        os.chmod(out, 0o755)
    shutil.rmtree(work, ignore_errors=True)
    print(f"zsign built: {out}")


if __name__ == "__main__":
    main()
