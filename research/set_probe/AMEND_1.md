# AMEND_1: the lookup gates the probe. Committed before any code is measured and before any run; never edited after.

Owner, 2026-11-12: "doesn't the map show which items would send out".

## Change to the probe variant
- **Outward files:** a file is outward when an import-style line of it names an outward-facing library:
  - network: socket, ssl, http, urllib, requests, httpx, aiohttp, websockets, ftplib, smtplib, paramiko, boto3, grpc, net/http, axios, node-fetch, fetch, net, dgram, open-uri;
  - process: subprocess, multiprocessing, child_process, os/exec, pty.
- **The gate:** an entry program that reaches an outward file, through the lookup, is never probed. The variant then behaves as set for the files only it reaches.
- **The backstop:** what is probed still runs in the temporary copy with no network. The lookup cannot see a shell string, a computed import or an environment switch.
- **Tests added:**
  - a program that imports `subprocess`, directly or through a module it uses, is not probed and its change is held as in set;
  - a program with no outward reach is probed.
- **Unchanged:** everything else in RULES.md.
