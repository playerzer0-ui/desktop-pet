# Desktop pet

spawn a desktop pet from the other world that u know nothing about

## requirements

- python 3.11 or newer

## steup

### windows

run setup.bat or setup.ps1

wait a bit

once all is ready, start.bat

### linux

you need these first (setup.sh tells you if one is missing):

- python 3.11 or newer, with venv (ubuntu / debian: `sudo apt install python3 python3-venv`)
- llama-server from llama.cpp: `brew install llama.cpp`, or a release from https://github.com/ggml-org/llama.cpp/releases with llama-server put in the `server/` folder
- qt's window library (ubuntu / debian: `sudo apt install libxcb-cursor0`)

then

```bash
bash setup.sh
```

and once all is ready

```bash
bash start.sh
```

on wayland, start.sh runs her in X11 mode (through XWayland), since wayland doesn't let apps place their own windows and she couldn't walk along the bottom of the screen