"""Puts the licenses of everything the built game ships (or downloads) into it: build.ps1 (Windows) and
build.sh (Linux) run this after PyInstaller.

    python build_notices.py dist\\DesktopPet

writes dist\\DesktopPet\\THIRD_PARTY_NOTICES.txt (who made what, under which license, where its source is) and
dist\\DesktopPet\\licenses\\ (each license's full text). Versions are read from what's installed, so the notice stays
right after an update. Texts that don't come with the installed packages are kept in licenses/ in the repo:
llama.cpp's, the Qwen model's, the LGPL / GPL (PySide6's wheels don't include them), and Python's (Linux Pythons
often don't ship it).
"""
import importlib.metadata as md
import os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
KEPT = os.path.join(HERE, "licenses")
WINDOWS = os.name == "nt"
EXE = "DesktopPet.exe" if WINDOWS else "DesktopPet"
SERVER = "llama-server.exe" if WINDOWS else "llama-server"
INSIDE = lambda *parts: os.path.join("_internal", *parts)  # (a path inside the build, as the notice writes it)

def python_license():
    """Python's own LICENSE.txt if this Python has one (Windows always does), else the copy kept in the repo."""
    for spot in (os.path.join(sys.base_prefix, "LICENSE.txt"), os.path.join(os.path.dirname(os.__file__), "LICENSE.txt")):
        if os.path.isfile(spot):
            return spot
    return os.path.join(KEPT, "Python-LICENSE.txt")

def package_files(name, pattern=r"LICENSE|COPYING|NOTICE"):
    dist = md.distribution(name)
    return dist.version, [dist.locate_file(f) for f in (dist.files or [])
                          if re.search(pattern, os.path.basename(str(f)), re.I) and "Qt-Commercial" not in str(f)]

def llama_version(server_dir):
    try:
        out = subprocess.run([os.path.join(server_dir, SERVER), "--version"], capture_output=True,
                             text=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        found = re.search(r"version:\s*(\S+)\s*\(build (\d+), commit ([0-9a-f]+)\)", out.stdout + out.stderr)
        return f"{found.group(1)}, build {found.group(2)}, commit {found.group(3)}" if found else "unknown build"
    except (OSError, subprocess.SubprocessError):
        return "unknown build"

def main(dest):
    licenses = os.path.join(dest, "licenses")
    shutil.rmtree(licenses, ignore_errors=True)
    os.makedirs(licenses)
    def keep(src, name):
        shutil.copyfile(src, os.path.join(licenses, name))
        return os.path.join("licenses", name)

    entries = []  # (title, lines)
    py = sys.version.split()[0]
    entries.append((f"Python {py}", [
        "The Python runtime the game runs on (%s and the standard library, in _internal)."
        % ("python%d%d.dll" if WINDOWS else "libpython%d.%d.so") % sys.version_info[:2],
        "License: Python Software Foundation License (PSF-2.0)", "Source: https://www.python.org/",
        "Full text: " + keep(python_license(), "Python-LICENSE.txt")]))

    pyside, _ = package_files("PySide6")
    entries.append((f"Qt for Python (PySide6 and shiboken6) {pyside}, and the Qt {pyside} libraries it includes", [
        "The windows, the speech bubble and the sprites on screen.",
        "License: GNU Lesser General Public License v3 (LGPL-3.0). The LGPL is a set of extra permissions on top",
        "of the GNU GPL v3, so both texts are included.",
        "Source: https://code.qt.io/cgit/pyside/pyside-setup.git (Qt for Python), https://download.qt.io/ (Qt)",
        f"Replacing them: the Qt and PySide6 libraries are separate files in {INSIDE('PySide6')} and",
        f"{INSIDE('shiboken6')}. You may replace them with your own builds of the same version.",
        "Qt itself contains third-party code (zlib, libpng, FreeType, HarfBuzz and others), listed with their",
        "licenses at https://doc.qt.io/qt-6/licenses-used-in-qt.html",
        "Full text: " + keep(os.path.join(KEPT, "LGPL-3.0.txt"), "LGPL-3.0.txt") + ", "
        + keep(os.path.join(KEPT, "GPL-3.0.txt"), "GPL-3.0.txt")]))

    for name, what, lic, url in (
            ("requests", "Downloading the model on first launch.", "Apache License 2.0", "https://github.com/psf/requests"),
            ("urllib3", "Used by requests.", "MIT License", "https://github.com/urllib3/urllib3"),
            ("certifi", "Used by requests (the trusted certificates for HTTPS).", "Mozilla Public License 2.0",
             "https://github.com/certifi/python-certifi"),
            ("idna", "Used by requests.", "BSD 3-Clause License", "https://github.com/kjd/idna"),
            ("charset-normalizer", "Used by requests.", "MIT License", "https://github.com/jawah/charset_normalizer")):
        version, files = package_files(name)
        texts = [keep(f, f"{name}-{os.path.basename(str(f))}") for f in files]
        entries.append((f"{name} {version}", [what, f"License: {lic}", f"Source: {url}",
                                              "Full text: " + ", ".join(texts)]))

    server = os.path.join(dest, "_internal", "server")
    entries.append((f"llama.cpp ({llama_version(server)})", [
        f"{SERVER} and its ggml / llama libraries (in {INSIDE('server')}): they run the model.",
        "License: MIT License, Copyright (c) 2023-2026 The ggml authors", "Source: https://github.com/ggml-org/llama.cpp",
        "Full text: " + keep(os.path.join(KEPT, "llama.cpp-LICENSE.txt"), "llama.cpp-LICENSE.txt")]))
    if os.path.exists(os.path.join(server, "LICENSE-LLVM-OpenMP")):  # (the Windows llama.cpp ships libomp.dll)
        entries.append(("LLVM OpenMP runtime", [
            f"libomp.dll (in {INSIDE('server')}), used by llama.cpp.",
            "License: Apache License 2.0 with LLVM Exceptions", "Source: https://github.com/llvm/llvm-project",
            "Full text: " + keep(os.path.join(server, "LICENSE-LLVM-OpenMP"), "LLVM-OpenMP-LICENSE.txt")]))
    if any(name.startswith("libgomp") for name in os.listdir(server)):  # (the Linux one uses GCC's, see build.sh)
        entries.append(("GNU OpenMP runtime (libgomp)", [
            f"libgomp.so.1 (in {INSIDE('server')}), used by llama.cpp. Part of GCC.",
            "License: GNU General Public License v3 with the GCC Runtime Library Exception, which lets programs",
            "that use it be shipped under any terms. Exception: https://www.gnu.org/licenses/gcc-exception-3.1.html",
            "Source: https://gcc.gnu.org/", "Full text: " + keep(os.path.join(KEPT, "GPL-3.0.txt"), "GPL-3.0.txt")]))

    entries.append(("Qwen3.5-4B (the language model)", [
        "The characters' minds. Not included in the game: it's downloaded on first launch, as the file",
        "Qwen3.5-4B-Q5_K_M.gguf, a GGUF conversion by Unsloth (https://huggingface.co/unsloth/Qwen3.5-4B-GGUF).",
        "License: Apache License 2.0, Copyright 2026 Alibaba Cloud", "Source: https://huggingface.co/Qwen/Qwen3.5-4B",
        "Full text: " + keep(os.path.join(KEPT, "Qwen3.5-4B-LICENSE.txt"), "Qwen3.5-4B-LICENSE.txt")]))

    pyinstaller, files = package_files("pyinstaller", r"COPYING")
    entries.append((f"PyInstaller {pyinstaller} (its bootloader, {EXE})", [
        f"Packs the game into {EXE}.",
        "License: GPL-2.0-or-later, with an exception that lets programs built with it be shipped under any terms.",
        "Source: https://github.com/pyinstaller/pyinstaller",
        "Full text: " + ", ".join(keep(f, f"PyInstaller-{os.path.basename(str(f))}") for f in files)]))

    if WINDOWS:
        entries.append(("Microsoft Visual C++ runtime", [
            "MSVCP140.dll, VCRUNTIME140.dll and the like (in _internal), which Python and Qt need.",
            "Shipped as Microsoft allows for its Visual C++ Redistributable files (they're Microsoft's, not open source).",
            "More: https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist"]))

    lines = ["THIRD-PARTY NOTICES", "", "Desktop Pet is built with the open-source software below. Each one's full",
             "license is in the licenses folder next to this file.", ""]
    for title, body in entries:
        lines += ["-" * 78, title, ""] + [f"  {line}" for line in body] + [""]
    with open(os.path.join(dest, "THIRD_PARTY_NOTICES.txt"), "w", encoding="utf-8", newline="\r\n" if WINDOWS else "\n") as f:
        f.write("\n".join(lines))
    print(f"wrote THIRD_PARTY_NOTICES.txt and {len(os.listdir(licenses))} license files into {dest}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "dist", "DesktopPet"))
