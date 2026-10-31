# Google Location Sharing Connector

Read the locations that people share with your Google account through
Google Maps Location Sharing — from the command line, with no official
API.

Google offers no API, API key, or OAuth scope for Location Sharing data.
This connector calls the same internal RPC the Google Maps web app calls
(`GET https://www.google.com/maps/rpc/locationsharing/read`), with the
contract reverse engineered from the open-source
[locationsharinglib](https://pypi.org/project/locationsharinglib/)
client (MIT) using [REA](https://github.com/morluto/rea) plus live
probes. The full contract — endpoint, `pb` parameter, payload index
map, and validation evidence — is in [docs/contract.md](docs/contract.md).

## What it does

- `gls people` — everyone sharing with you: name, address, coordinates,
  accuracy, location age, phone battery and charging state.
- `gls person "<name>"` / `gls locate "<name>"` — one person's record.
- `gls auth status` / `gls auth import <cookies.txt> --account <email>`
  — session management.

Read-only. Prints to stdout only; persists nothing about the people it
reads. Cookie values are never printed or logged.

## Auth: session cookies, because there is no other way

Auth is a Netscape-format `cookies.txt` exported from a browser signed
in to the Google account that receives the shares. Treat the file as a
password equivalent: it is a full Google session. Signing out of Google
anywhere invalidates it.

`tools/` contains the session-minting setup used by the author: a local
open-source Chromium driven by Playwright (`drive_signin.py`,
`gls-browser.sh`) that completes one full sign-in session and exports
its own cookies, a minimal CONNECT forwarder (`local_proxy.py`) for
proxied sandboxes whose CA the Chromium build does not trust, and
`lane5_pipe.py`, which feeds a password from a Google Password Manager
CSV export to the sign-in over stdin only — the export is shredded
before parsing, only the google.com row is read, and the value is never
printed, written, or logged.

## One hard-won detail: session validation

The source client's validation rule — "myaccount.google.com answers
without a redirect, so the session is live" — is wrong in practice. A
verified-live session still 302s through `ServiceLogin` and
`SetOSID` before landing back on myaccount, so redirect history cannot
distinguish live from dead. This connector validates against the read
RPC itself: the session is live iff the payload returns in
authenticated shape (element `[0]` is a list; unauthenticated responses
have `[0] = null`). Verified live 2026-10-29.

## Layout

- `bin/gls` — the CLI (Python 3 + `requests`, no other dependencies)
- `CONNECTOR.md` — the connector document (usage, credentials, errors)
- `docs/contract.md` — the reverse-engineered RPC contract
- `tools/` — local-Chromium session minting (Playwright)

## Disclaimer

Unofficial. The endpoint is undocumented and can change or stop working
without notice. Use only with accounts and shares you are authorized to
read.

## License

MIT

## Install it with Muse

Just give this prompt to your Muse:

> "Install Google Location Sharing Connector from https://github.com/jonathancruzate/google-location-sharing-connector — read the README, install it, set it up for me, and show me how to use it."

