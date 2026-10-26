# PyInstaller recipe for the Windows game (build.ps1 runs it): one folder, dist\DesktopPet\, with DesktopPet.exe
# and an _internal\ folder holding Python, Qt, the code, the characters and llama-server (in server\, where
# server.py looks first). The model isn't in it: it's downloaded on first launch (desktop/download.py) into the
# player's data folder (config.DATA), like everything else the game writes.
# One folder rather than one exe: a one-file build unpacks itself to a temp folder on every launch, which is slow
# and trips antivirus programs far more often.
import os

here = os.path.abspath(SPECPATH)
server = os.path.join(here, "build", "llama-server")  # (build.ps1 copies llama-server's files here first)
server_files = sorted(os.listdir(server))

a = Analysis(
    [os.path.join(here, "main.py")],
    pathex=[here],
    binaries=[(os.path.join(server, f), "server") for f in server_files if f.lower().endswith((".exe", ".dll"))],
    datas=[(os.path.join(here, "character"), "character")]
          + [(os.path.join(server, f), "server") for f in server_files if not f.lower().endswith((".exe", ".dll"))],
    excludes=["tkinter", "test_pip", "tests"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="DesktopPet",
    console=False,  # (no black window: errors are shown in a message box, see main.py)
    icon=os.path.join(here, "build", "icon.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="DesktopPet", upx=False)
