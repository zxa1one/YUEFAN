# YUEFAN · Dining together

[简体中文](README.md)

A mobile-first collaborative dining decision tool combining real location data, budgets, fair-distance ranking and group voting. The host creates a shared room and friends join by invitation without registration.

## Highlights

- Rooms for 2–12 people; guests request browser location on entry. The host can begin only once all planned members have joined and provided a location.
- Real Amap restaurant discovery (20 km default), budget-aware ranking, and separate price sorting.
- Live member and voting status, one vote per member token, host-only early finish, final results with voter names and alphabetical tie-breaking (Chinese pinyin).
- Responsive Apple-inspired interface, light/dark/system themes, text size, language and reduced-motion preferences.

## Run locally

Requires Python 3.9+ (standard library only) and an Amap Web Service API key. Python 3.13 and Node 22 were used for the release checks.

```sh
python3 setup_amap.py
python3 server.py
```

Open http://127.0.0.1:8000. The setup script validates the key and saves it locally. Alternatively inject `AMAP_KEY` as an environment variable. Never commit credentials or the SQLite database. On Windows, use `py -3` or `python` if `python3` is unavailable.

For a small, controlled phone test, use a trusted HTTPS tunnel. With cloudflared installed:

```sh
cloudflared tunnel --protocol http2 --url http://127.0.0.1:8000
```

Both the host and guests use the generated HTTPS origin. Keep the server and tunnel running. Phone geolocation requires a secure context and user consent. The temporary domain can change and may not be reachable on every network. This is not a production deployment.

## Ranking

Fair distance = 70% mean straight-line distance + 30% maximum straight-line distance. The recommendation score uses approximately 95.66% rating and 4.34% normalized distance utility; unsupported popularity and sales metrics are excluded. A ±20% budget band receives priority in composite sorting, and opening status also affects ordering. Final results are ranked solely by votes, then name A–Z.

## Tests

Run `python3 -m unittest -v`, `node --check public/app.js`, and each `test_*.cjs` script. This release candidate passed 38 Python tests and four front-end check scripts. Live map requests and real phones are not covered by these automated tests; browser rendering was blocked by the build environment.

## Privacy, limitations and license

Locations and membership tokens are stored in a local SQLite database; map providers receive coordinates required for lookup. Member distances may reveal approximate locations. See [SECURITY.md](SECURITY.md). This is a self-hosted prototype, not a hardened public service. Demo data is disabled by default and enabled explicitly only for developer tests. The normal UI never silently substitutes mock restaurant data.

Product design and rules were led by the project initiator, with AI-assisted implementation. The project's license is pending owner approval; third-party notices are retained in [PINYIN-NOTICE.txt](PINYIN-NOTICE.txt). Map data and third-party content are not covered by a future source-code license.
