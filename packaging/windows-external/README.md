# Windows external runtime launcher

These files belong in the root of a portable distribution, with the scripts under `launcher/`, backend and migration scripts under `app/src/backend` and `app/scripts`, and built frontend under `app/web`.

Keep `src/backend/portable_bootstrap.py` in the packaged backend directory. It ensures an embedded Python runtime uses the packaged backend rather than source bundled with that runtime.

Optional `launcher/local-runtime.json` contains personal runtime paths, and must not be committed. Its fields are `python`, `java`, and `neo4j`. API credentials are encrypted with Windows DPAPI in `%LOCALAPPDATA%/SmartSketch-External/api-settings.json` and are never included in this repository. API and worker read the same settings after restart.
