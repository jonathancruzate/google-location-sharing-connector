#!/usr/bin/env python3
"""Lane-5 pipe for the GLS local-browser sign-in.

Per the Secure Password Process (~/workspace/security/secure-password-process.md),
lane 5: given a Google Password Manager CSV export on local disk,
extract ONLY the google.com row in memory, start the one-session
sign-in driver, and pipe the password to its stdin. The value is never
printed, written to a file, or logged. The CSV is shredded immediately
after extraction, before the sign-in even runs.

Usage: lane5_pipe.py <export.csv>
Prints metadata only: row found (site, username), shred confirmation.
"""
import csv
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET_SITES = ("google.com", "accounts.google.com")


def shred(path):
    size = os.path.getsize(path)
    with open(path, "r+b") as fh:
        fh.write(os.urandom(size))
        fh.flush()
        os.fsync(fh.fileno())
    os.unlink(path)
    return not os.path.exists(path)


def main():
    if len(sys.argv) != 2:
        print("usage: lane5_pipe.py <export.csv>")
        sys.exit(2)
    csv_path = sys.argv[1]
    if not os.path.exists(csv_path):
        print(f"file not found: {csv_path}")
        sys.exit(2)

    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        text = fh.read()
    # Shred FIRST, before anything else can copy or cache the export.
    gone = shred(csv_path)
    print(f"export shredded and verified deleted: {gone} ({os.path.basename(csv_path)})", flush=True)

    rows = list(csv.DictReader(io.StringIO(text)))
    text = None
    candidates = []
    for row in rows:
        url = (row.get("url") or "").lower()
        name = (row.get("name") or "").lower()
        if any(site in url or site == name for site in TARGET_SITES):
            candidates.append(row)
    rows = None
    match = None
    for row in candidates:
        if (row.get("username") or "").lower() == os.environ.get("GLS_TARGET_USERNAME", ""):
            match = row
            break
    if match is None and candidates:
        match = candidates[0]
    candidates = None
    if not match:
        print("no google.com row found in the export")
        sys.exit(3)
    username = match.get("username") or ""
    password = match.get("password") or ""
    match = None
    if not password:
        print(f"google.com row found for {username} but it carries no password")
        sys.exit(3)
    print(f"row extracted in memory: site=google.com username={username}", flush=True)

    env = dict(os.environ)
    env["GLS_TIMEOUT"] = "900"
    cmd = os.environ.get("GLS_SIGNIN_CMD", os.path.join(HERE, "gls-browser.sh") + " full").split()
    # Up to 2 driver attempts inside this one process, so a flaky page
    # transition does not kill the run: the value stays in memory here
    # and is re-piped on a retry, and dies with this process regardless.
    attempts = 2
    last_rc = 1
    for attempt in range(1, attempts + 1):
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, env=env,
        )
        sent = False
        exported = False
        assert proc.stdout is not None and proc.stdin is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            if "READY_FOR_PASSWORD" in line and not sent:
                proc.stdin.write(password + "\n")
                proc.stdin.flush()
                sent = True
            if '"exported"' in line:
                exported = True
        proc.wait()
        last_rc = proc.returncode
        print(f"attempt {attempt}: driver exit code: {last_rc}, password piped: {sent}, cookies exported: {exported}", flush=True)
        if exported:
            break
        if attempt < attempts:
            print("retrying sign-in once with the value still in memory...", flush=True)
    password = None
    sys.exit(0 if exported else last_rc)


if __name__ == "__main__":
    main()
