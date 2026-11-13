"""[ADDED] D-terminal SIM-only TWIST2 gate control; no G1 hardware."""
import os
import select
import socket
import sys
import termios
import tty

PORT = 9893


def main():
    if not sys.stdin.isatty():
        raise SystemExit('[error] Terminal D must be an interactive TTY for ]/Enter controls')
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    original = termios.tcgetattr(sys.stdin.fileno())
    print('\n[TWIST2 Xsens SIM] G1 initial pose is held (physics paused).', flush=True)
    print('  ] : ARM policy (no teleop yet)\n  Enter : start / pause / resume teleop\n  Ctrl+C : quit simulation', flush=True)
    try:
        tty.setcbreak(sys.stdin.fileno())
        while True:
            r, _, _ = select.select([sys.stdin], [], [], 0.2)
            if not r:
                continue
            key = os.read(sys.stdin.fileno(), 1)
            if key == b']':
                sock.sendto(b'ARM', ('127.0.0.1', PORT))
                print('\n[controller] ] -> policy armed; press Enter for teleop', flush=True)
            elif key in (b'\r', b'\n'):
                # [CHANGED] State machine owns the toggle; keyboard never guesses state.
                sock.sendto(b'TOGGLE', ('127.0.0.1', PORT))
                print('\n[controller] Enter -> teleop toggle requested', flush=True)
    finally:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, original)
        sock.close()


if __name__ == '__main__':
    main()
