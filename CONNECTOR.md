# Google Location Sharing

- `custom.google-location-sharing` connects Muse to the location data that other Google accounts share with the user's Google account through Google Maps Location Sharing, plus the user's own shared location.

- There is no official Google API, API key, or OAuth scope for this data. The connector calls the same internal RPC the Google Maps web app calls, reverse engineered with REA on 2026-10-28. The full contract, with its evidence and live probes, lives in the [REA dossier](docs/contract.md).

- The helper is `bin/gls`, a Python 3 CLI that uses `requests`. It is read-only and prints locations to stdout only. It persists nothing about the people it reads.

## Connect

- This connector was not registered through the hosted credential flow because Google offers no API key or OAuth program for Location Sharing. Auth state lives in a local file beside the CLI instead, as described under Credentials. That matches the Resy connector pattern.

- To mint the session, sign in to Google in a browser as the account that receives the shares, open google.com/maps, and export the cookies for google.com in Netscape cookies.txt format with a cookie-export extension. The export happens on the user's own machine.

- Import the exported file and record which account it belongs to.

```text
bin/gls auth import <path-to-cookies.txt> --account <account email>
```

- Prove access with a harmless read before the first use in a conversation.

```text
bin/gls auth status
bin/gls people
```

## Credentials

- Every request carries the Google session cookies from `~/workspace/custom-connectors/custom.google-location-sharing/cookies.txt`. The CLI loads that file with mode 600 and never prints a cookie value, a cookie header, or a session token.

- The cookie file is a full Google session and is a password equivalent. Never put it, or any value from it, in this doc, a command argument, an environment variable, a log, a memory file, or chat. Never ask the user to paste cookie values in chat.

- `config.json` beside the CLI holds only non-secret settings, the account email and the `authuser` slot. It is stored with mode 600 as well.

- The `authuser` slot says which signed-in Google account in a multi-login browser profile to read. It defaults to 0. The older reverse-engineered client hard-coded 2, so set this if reads come back empty while the session validates.

- Signing the account out of Google in any browser invalidates the exported cookies. When the session dies, export a fresh cookies.txt and import it again.

- On an invalid session the CLI exits with code 3 and says so plainly. Check the session with `gls auth status` before assuming the endpoint or a person's sharing changed.

## List everyone sharing

- Read every person sharing with this account, plus the account's own location when Google returns one.

```text
bin/gls people
```

- The output is JSON with a `count` and a `people` array. Each person carries `full_name`, `nickname`, `latitude`, `longitude`, `timestamp_ms`, `datetime_utc`, `age_seconds`, `accuracy_m`, `address`, `country_code`, `charging`, and `battery_level`. The `source` field reads `shared` for other people and `authenticated_account` for the user's own location.

- Entries whose location tuple is missing are dropped, matching the source client's behavior. A person who paused sharing or whose phone is off may be absent entirely rather than listed with a stale fix.

## Read one person

- Read the full record for one person by full name or nickname. Matching is case-insensitive and exact.

```text
bin/gls person "<full name>"
```

- Read just the coordinates, address, and freshness for one person.

```text
bin/gls locate "<full name>"
```

- When nobody matches, the CLI exits with code 5 and lists the full names it did see, so a spelling or nickname mismatch is visible right away.

## Check the session

- Validate the imported cookies against Google without printing any values.

```text
bin/gls auth status
```

- The output reports whether the cookies file exists, how many Google cookies it carries and their names, the earliest Google cookie expiry, and whether the session is live. The live check probes the read RPC itself: the session counts as live only when the payload comes back in authenticated shape (element [0] is a list). Do NOT substitute the source client's myaccount rule: live-verified 2026-10-29, a valid session still redirects through ServiceLogin and SetOSID before landing back on myaccount, so redirect history cannot tell a live session from a dead one here.

## Recover from errors

- Exit code 2 means no cookies file has been imported yet, or the import carried no Google cookies. Export and import a fresh cookies.txt.

- Exit code 3 means the cookies no longer carry a live session. Re-export from a signed-in browser and import again. Do not retry reads against a dead session.

- Exit code 4 means the read endpoint answered with something the parser could not use. The endpoint is undocumented and its payload shape can change. Re-check the contract in the REA dossier before changing the parser.

- An empty `people` list with a valid session means nobody is currently visible. Check the `authuser` slot first, then check in Google Maps itself whether sharing is still on.

- A bare HTTP 200 from the endpoint proves nothing on its own. A live probe with no cookies on 2026-10-28 also returned 200 with null people, so always pair reads with the session check the CLI performs.

## Limits

- This connector is read-only. It cannot start, stop, or change a share, and it cannot read anyone who has not shared their location with the user's account.

- Locations are only as fresh as each person's phone last reported. Always read `age_seconds` before describing a location as current.

- The endpoint is unofficial and can change or stop working without notice. The parser index map in the REA dossier is the record to re-verify against when it does.

- Reading the user's own location through this lane is untested until a session is imported. The own-location record is built from a different part of the payload than the shared entries.

## Related skills

- [REA, StephAI bindings](~/workspace/custom-skills/local-rea/SKILL.md)

- Use `muse.skill_search` to find other skills and `muse.connector_search` to find other connectors.
