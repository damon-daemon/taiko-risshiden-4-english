"""Keyboard input for the headless PCSX2, isolated from every other program.

headless.sh runs PCSX2 (Qt, xcb) inside a headless gamescope, which gives it a private
Xwayland server. XTEST key events sent to that X display reach only that PCSX2: not
the desktop, not another project's emulator (2026-11-08: a DuckStation session ran
next to ours; virtual uinput gamepads were seen by both emulators, so button presses
clashed). The headless PCSX2 has SDL input off, so it ignores other pads too.

usage: xkeys.py hold KEY MS      press KEY (X keysym name, e.g. x, Return, Up) for MS ms
       xkeys.py display          print our PCSX2's X display
       xkeys.py wayland          print our gamescope's socket (for screenshots)
Uses libX11 + libXtst through ctypes (no extra packages).
"""
import ctypes, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MARK = os.path.join(ROOT, 'build', 'pcsx2h')

def pcsx2_env():
    """Environment of our headless PCSX2: the process whose command line STARTS with
    the PCSX2 binary (gamescope's own command line contains it too, and gamescope has
    the desktop's DISPLAY) and that runs under gamescope (GAMESCOPE_WAYLAND_DISPLAY set)."""
    pids = subprocess.run(['pgrep', '-f', '^[^ ]*pcsx2[^ ]* -datapath ' + MARK],
                          capture_output=True, text=True).stdout.split()
    for pid in pids:
        try:
            env = dict(e.split(b'=', 1) for e in
                       open('/proc/%s/environ' % pid, 'rb').read().split(b'\0') if b'=' in e)
        except OSError:
            continue
        if b'GAMESCOPE_WAYLAND_DISPLAY' in env and b'DISPLAY' in env:
            return {k.decode(): v.decode() for k, v in env.items()}
    sys.exit('headless PCSX2 not running')

def display():
    """DISPLAY of our headless PCSX2 (gamescope's private Xwayland)."""
    return pcsx2_env()['DISPLAY']

def hold(key, ms):
    x11 = ctypes.CDLL('libX11.so.6')
    xtst = ctypes.CDLL('libXtst.so.6')
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XStringToKeysym.restype = ctypes.c_ulong
    x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
    x11.XKeysymToKeycode.restype = ctypes.c_ubyte
    x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XFlush.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    d = x11.XOpenDisplay(display().encode())
    if not d:
        sys.exit('cannot open the headless X display')
    sym = x11.XStringToKeysym(key.encode())
    code = x11.XKeysymToKeycode(d, sym) if sym else 0
    if not code:
        sys.exit('unknown key %r' % key)
    xtst.XTestFakeKeyEvent(d, code, 1, 0)
    x11.XFlush(d)
    time.sleep(ms / 1000)
    xtst.XTestFakeKeyEvent(d, code, 0, 0)
    x11.XFlush(d)
    x11.XCloseDisplay(d)

if __name__ == '__main__':
    if sys.argv[1] == 'display':
        print(display())
    elif sys.argv[1] == 'wayland':
        print(pcsx2_env()['GAMESCOPE_WAYLAND_DISPLAY'])
    elif sys.argv[1] == 'hold':
        hold(sys.argv[2], int(sys.argv[3]))
