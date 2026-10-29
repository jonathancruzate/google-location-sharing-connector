# Google Maps Location Sharing — RPC contract dossier

Distilled 2026-10-28 (REA session, at the account owner's request — "Use rea repo to
create a Google location sharing connector") from the de-facto
reverse-engineered client `locationsharinglib` 4.2.0 (costastf, MIT) plus
live probes of the production endpoint. Purpose: read the locations that
other Google accounts share with the owner's Google account (and their own
shared location) from Muse. Every claim below has a source-code or
live-probe basis.

Method note, per the REA program's verify-before-trust rule: REA
`inspect-artifact` on the locationsharinglib sdist returned
`target_unavailable / unsupported binary format` (it is a source tarball,
and REA's own skill says to skip REA for ordinary source analysis). REA
`analyze-javascript-application` on the extracted client directory
completed and inventoried the artifact — Evidence
`ev_ea6520d4a35128a23b9cf4c39e0e706eed333338875a172230fe2117ac90bed4`,
root sha256 `598553e2e7dae606f1bd7d3562da88bad10701de8f73c7db7e7a4be84a5cd1ea`,
inventory graph `98d3ef77904d30639dda6547cebeca8a9bdb814fd214a4ca49338e9f84ad03c9`
— with zero JavaScript modules found, as expected for a Python client.
The Google Maps web homepage loads its bundles dynamically (a plain
fetch returns bootstrap JSON with no static script URLs to capture), so
no static Maps bundle was analyzable that way. The contract below
therefore rests on targeted extraction of the client code that speaks
the protocol, with the decisive claims reproduced by live probes — the
same basis as the SPR dossier (spr-api-contract.md). An Android-APK deep
dive (REA jadx lane) was not needed: the web RPC contract is fully
specified by the client source and confirmed live.

## There is no official API

Google offers no public API, API key, or OAuth scope for reading
Location Sharing data. The only route is the internal RPC the Google
Maps web app itself calls, authenticated by the signed-in session's
cookies. Consequences:

- Muse's hosted credential flow cannot register this connector: it
  supports API keys and OAuth 2.0 authorization-code flows and declines
  session-cookie schemes. Like Resy, this connector keeps its auth state
  in a local file beside the CLI, mode 600, and never prints it.
- Signing the account out anywhere invalidates the cookies.
- The cookie file is a full Google session. Treat it like a password:
  mode 600, never in chat, logs, memory, or git.

## The read endpoint (client code, explicit)

`GET https://www.google.com/maps/rpc/locationsharing/read`

Query parameters (locationsharinglib 4.2.0 `Service._get_data`):

- `authuser` — which signed-in Google account slot to read. The library
  hard-codes `2`; most single-account and Home Assistant setups use
  `0`. It must match the account the cookies belong to in a
  multi-login browser profile. The connector defaults to `0` and makes
  it configurable.
- `hl=en`, `gl=us`
- `pb` — a constant protobuf-style rendering blob that points at
  Google HQ and is irrelevant to the sharing data:
  `!1m7!8m6!1m3!1i14!2i8413!3i5385!2i6!3x4095!2m3!1e0!2sm!3i407105169!3m7!2sen!5e1105!12m4!1e68!2m2!1sset!2sRoadmap!4e1!5m4!1e4!8m2!1e0!1e1!6m9!1e12!2i2!26m1!4b1!30m1!1f1.3953487873077393!39b1!44e1!50e0!23i4111425`

An earlier endpoint generation used `/maps/preview/locationsharing/read`
(lib changelog 4.1.1, 2020-04-22: "Updated endpoint to rpc from
preview"). The `preview` path is superseded.

## Response shape (client code, explicit)

- Body opens with the anti-XSSI prefix `)]}'` followed by a newline,
  then a JSON array. The library parses `response.text.split("'", 1)[1]`
  as JSON.
- Top level `[0]` — array of shared-people entries, or null when nobody
  is visible (or no valid session).
- Top level `[9][1]` — the authenticating account's own location tuple,
  in the same inner shape as a shared entry's `[1]`.
- Per shared entry (the `Person._populate` index map):
  - `[6][0]` Google account id, `[6][1]` picture URL, `[6][2]` full
    name, `[6][3]` nickname
  - `[1][1][2]` latitude, `[1][1][1]` longitude (the `[1][1]` pair is
    [unknown, longitude, latitude])
  - `[1][2]` timestamp, milliseconds since epoch
  - `[1][3]` accuracy in metres, `[1][4]` human-readable address,
    `[1][6]` country code
  - `[13][0]` charging flag, `[13][1]` battery percent; index 13 is
    absent on some devices, and both fields are optional
- Entries with a missing location tuple raise InvalidData in the
  library and are dropped. The connector does the same.

## Session validation (client code, explicit)

`GET https://myaccount.google.com/?hl=en` with the session cookies. If
the response history shows a redirect (to the sign-in flow), the
cookies are invalid and the library raises InvalidCookies. A clean 200
with no redirect history means the session is live.

## Live probes, 2026-10-28

- `GET /maps/rpc/locationsharing/read` with the full parameter set and
  NO cookies returned HTTP 200, content-type
  `application/json; charset=utf-8`, body starting `)]}'` then
  `[null,null,"<token>","<token>",null,null,"GgA=",1800,<ms epoch>]`.
  The route is alive and cookie-gated by data, not by status code: an
  unauthenticated call succeeds with null people, so callers must
  validate the session separately (above) instead of trusting a 200.
- `GET https://myaccount.google.com/?hl=en` without cookies returned
  HTTP 302 to an intro page, confirming the redirect signal the
  validation check relies on is observable from this VM.

## Auth mint

1. In a browser signed in to the Google account that receives the
   shares, open google.com/maps.
2. Export the cookies for google.com in Netscape cookies.txt format
   (for example with a "Get cookies.txt" style extension, which writes
   the file locally on the user's own machine).
3. Import that file into the connector with `gls auth import`. The CLI
   checks it carries google.com cookies, stores it mode 600 beside the
   CLI, and records only the account email and authuser slot as config.
4. Verify with `gls auth status`, which validates the session live and
   reports cookie count and earliest expiry without any values.

Cookies rotate and die. When reads start returning an invalid session,
re-export and re-import. Signing out of Google in any browser kills
the exported session too.

## Connector built on this contract

`~/workspace/custom-connectors/custom.google-location-sharing/` — the
`gls` CLI reimplements the parser from the index map above in stdlib +
requests, with no dependency on locationsharinglib and no pickle
loading. Read-only: there is no write/share/stop-sharing operation in
this contract. The CLI prints locations to stdout only and persists
nothing about the people it reads.

## Correction 2026-10-29 — session validation rule (live evidence)

The locationsharinglib myaccount rule ("no redirect history = valid") is
WRONG for this network/account. A session verified live (the read RPC
returned 5 shared people, payload parsed cleanly) still produced a
myaccount redirect chain: 302 myaccount → 302 accounts.google.com/
ServiceLogin → 302 myaccount/accounts/SetOSID → 200 myaccount. The
connector's validation was changed to probe the read RPC itself:
authenticated shape = HTTP 200 + anti-XSSI prefix + element [0] is a
list; the unauthenticated shape has [0] = null. First live read:
2026-10-29 00:44 EDT, 6 parsed entries (5 shared + own location).
