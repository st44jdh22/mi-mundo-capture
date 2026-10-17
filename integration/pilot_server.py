"""Synthetic-only pilot entrypoint. No permanent storage or departmental routing."""
import os
import tempfile
from receiver import FixtureStore, make_server

token = os.environ["MI_MUNDO_TEST_TOKEN"]
origin = os.environ.get("MI_MUNDO_ORIGIN", "https://st44jdh22.github.io")
port = int(os.environ.get("PORT", "8080"))
if len(token) < 32:
    raise SystemExit("Missing valid test token")
with tempfile.TemporaryDirectory(prefix="mi-mundo-synthetic-") as directory:
    server = make_server(FixtureStore(directory), token, origin, port, host="0.0.0.0")
    print("Synthetic test receiver running. Temporary storage only; no production filing.", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
