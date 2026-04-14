#!/usr/bin/env python3
"""
Standalone CLI utility to send a test print directly to the thermal printer.

Usage:
    python test_print.py
    python test_print.py --host 10.42.10.100 --port 9100
    python test_print.py --text "Hello from the mesh!"
"""

import argparse
import socket
import sys
from datetime import datetime, timezone

# ESC/POS commands
ESC = b"\x1b"
GS = b"\x1d"
INIT = ESC + b"@"
BOLD_ON = ESC + b"\x45\x01"
BOLD_OFF = ESC + b"\x45\x00"
ALIGN_CENTER = ESC + b"\x61\x01"
ALIGN_LEFT = ESC + b"\x61\x00"
SIZE_NORMAL = GS + b"\x21\x00"
SIZE_DOUBLE_H = GS + b"\x21\x01"
CUT_PARTIAL = GS + b"V\x01"
FEED = ESC + b"d\x04"

WIDTH = 48


def build_test_receipt(custom_text=None):
    """Build a test receipt as bytes."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    sep = "=" * WIDTH

    parts = [
        INIT,
        ALIGN_CENTER,
        SIZE_DOUBLE_H, BOLD_ON,
        b"PRINTER TEST\n",
        BOLD_OFF, SIZE_NORMAL,
        (sep + "\n").encode(),
        ALIGN_CENTER,
        b"*** TEST PRINT ***\n",
        b"\n",
        f"Timestamp: {ts}\n".encode(),
        b"\n",
        (sep + "\n").encode(),
        b"Character test:\n",
        b"ABCDEFGHIJKLMNOPQRSTUVWXYZ\n",
        b"abcdefghijklmnopqrstuvwxyz\n",
        b"0123456789\n",
        b"!@#$%^&*()-_=+[]{}\n",
        (sep + "\n").encode(),
        BOLD_ON, b"BOLD TEXT\n", BOLD_OFF,
        SIZE_DOUBLE_H, b"DOUBLE HEIGHT\n", SIZE_NORMAL,
        (sep + "\n").encode(),
    ]

    if custom_text:
        parts.extend([
            b"\n",
            b"Custom message:\n",
            ("-" * WIDTH + "\n").encode(),
            custom_text.encode("utf-8"),
            b"\n",
            ("-" * WIDTH + "\n").encode(),
        ])

    parts.extend([
        b"\n",
        b"If you can read this, the printer\n",
        b"is working correctly.\n",
        b"\n",
        f"Thermal Printer Terminal\n".encode(),
        ALIGN_LEFT,
        FEED,
        CUT_PARTIAL,
    ])

    return b"".join(parts)


def send_to_printer(data, host, port, timeout):
    """Send raw bytes to the printer over TCP."""
    print(f"Connecting to {host}:{port}...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        print(f"Connected. Sending {len(data)} bytes...")
        sock.sendall(data)
        sock.close()
        print("Done! Print job sent successfully.")
    except socket.timeout:
        print(f"ERROR: Connection to {host}:{port} timed out after {timeout}s", file=sys.stderr)
        sys.exit(1)
    except ConnectionRefusedError:
        print(f"ERROR: Connection refused at {host}:{port}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Send a test print to the thermal printer")
    parser.add_argument("--host", default="printer.local.mesh",
                        help="Printer hostname or IP (default: printer.local.mesh)")
    parser.add_argument("--port", type=int, default=9100,
                        help="Printer port (default: 9100)")
    parser.add_argument("--timeout", type=int, default=10,
                        help="Connection timeout in seconds (default: 10)")
    parser.add_argument("--text", default=None,
                        help="Custom text to include in the test print")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build the receipt and print hex dump without sending")
    args = parser.parse_args()

    data = build_test_receipt(args.text)

    if args.dry_run:
        print(f"Receipt size: {len(data)} bytes")
        print("Hex dump:")
        for i in range(0, len(data), 16):
            hex_part = " ".join(f"{b:02x}" for b in data[i:i+16])
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in data[i:i+16])
            print(f"  {i:04x}: {hex_part:<48s} {ascii_part}")
        return

    send_to_printer(data, args.host, args.port, args.timeout)


if __name__ == "__main__":
    main()
