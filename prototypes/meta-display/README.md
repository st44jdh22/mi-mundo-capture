# HS-META-001: capture feasibility and local synthetic prototype

Status: **TESTED LOCALLY (transport harness); PREPARED (native Display view)**.
Nothing installed on glasses, phone or Railway. No production/real-media intake.
This directory is implementation evidence for existing issue #14, not a new app
repository or institutional record. Review baseline: main `3d833e61391925138f8c1fac572b30671c6a6470`.

## Technical verdict

The recommended capture route is an **iOS companion using Meta DAT**, showing the
three choices and Send on the glasses through `MWDATDisplay`. A simple web app is
useful for display/input/networking, but is not an established photo/video/raw
audio capture route. Do not equate dictated text input with an audio recording.
Do not promise phone-free *operation* until locked/background tests pass; a phone
companion does not necessarily require touching the phone for each capture.

| Requirement | Evidence and limitation |
| --- | --- |
| Display UI | DAT DisplayAccess sample sends interactive views; web apps also run on Display |
| Band selection / Send | Use Display Button callbacks first; raw Inputs is experimental and requires capability approval |
| Photo | CameraAccess captures photos; stream photo and standalone high-quality `camera.photo` are different paths; standalone photo is experimental |
| Video with sound | CameraAccess records video; glasses PCM audio alongside Camera Stream is experimental |
| Audio-only file | Investigate retaining PCM while Camera Stream runs; independent mic-only recording not established by this review; do not silently substitute phone mic or transcription |
| Original bytes | Preserve exactly what SDK supplies; an app-encoded stream recording is not necessarily the glasses' built-in camera original |
| Shortcut / voice launch | Voice Invocations is experimental with capability/name approval; no quick-launch entitlement assumed |
| Background / sleep | Current CameraAccess sample tears down on iOS backgrounding; continuous locked-phone use is an unresolved acceptance gate |
| Installation | Developer Mode, Meta AI registration, compatible firmware and approved camera/mic permissions; iOS signing and a Mac build required |
| Publishing | Experimental features cannot currently be published; a private developer test is distinct from public distribution |

Sources checked 5 November 2026, official Meta material:

- https://developers.meta.com/wearables/faq/ (says DAT 1.0 stable and Display supported).
- https://developers.meta.com/wearables/web-apps/ (display, gestures, text composer, networking; not proof of raw camera/mic access).
- https://github.com/meta/meta-wearables-dat-ios at `bbae597cd1c748cd29b9375a1624a8d75b1c9e14`;
  `AGENTS.md`, `CHANGELOG.md`, `samples/CameraAccess/README.md`,
  `samples/DisplayAccess/README.md` and `CarMaintenanceDisplay.swift` inspected.
- https://github.com/meta/meta-wearables-webapp/issues/33 is an open user report of
  camera API restrictions, **not** a Meta permission grant or definitive roadmap.

Some Meta marketing/FAQ and repository text disagree: repository README still
says developer preview, FAQ says 1.0 stable; historical 0.9 changelog mentions
background recording, current CameraAccess README/code guidance ends on background.
Use exact SDK build/firmware and physical test results, not the most optimistic text.
Authenticated developer pages were sign-in gated in public retrieval. No account,
permission, firmware, app registration or developer-mode change was performed.

## What is implemented

- `integration/meta_display_harness.py`: generates a fabricated PNG, one-second
  MP4 **with a silent audio track**, or one-second silent PCM WAV. No live capture.
- Existing v0.3 manifest and `validate_job.py`, existing `receiver.py` FixtureStore,
  and existing `capture-client.mjs` are reused unchanged. PUT `/v1/jobs/{uuid}`,
  then authenticated GET for independent receipt readback. No new backend or DB.
- Three-choice desktop UI and Send, keyboard/Enter navigation, red unverified /
  amber local-pending / green **TEST ONLY** receipt. It is not Meta's simulator
  or a deployable Meta web app. A restart/reload can retry the same saved package.
- Stable UUIDs, SHA-256/size/type and UTC fixture-generation time in the package;
  receiver time is separate. Raw media is checked independently in tests.
- `MetaCaptureMenu.swift`: real DAT Display DSL view functions for later host
  integration; callbacks have no invented SDK calls. **Not compiled or linked**.
  It is not a complete native application and captures/uploads nothing itself.

Local harness files are synthetic and persist in an explicit test folder outside
the repo until removed. Session credentials remain memory-only and rotate on
restart. FixtureStore is test storage, without private encryption, multi-process
guarantees, object-store backup/restore or power-loss qualification. HTTP is
loopback-only; no tunnel/public listener, arbitrary file importer or cloud route.

## Run and verify

Python 3.11+, Node 20+ (tested Node 24), ffmpeg and ffprobe needed:

```sh
python3 -m unittest discover -s integration -v
node --test integration/test_capture_client.mjs
python3 integration/meta_display_harness.py --synthetic \
  --workspace /tmp/hs-meta-synthetic-review --port 8767
```

Open http://127.0.0.1:8767/ **on that same machine**. This URL is not accessible
from Stephen's phone/glasses. Stop with Ctrl-C; do not expose it with a tunnel.
The checked-in tests prove transport and exact destination-byte readback using
generated media, duplicates, restarted client/store, offline failure, corruption,
wrong authentication/origin/host and conflicting same-ID data. Video is probed
for an actual video+audio stream. They do not prove glasses/phone capture.
Browser interaction/render QA remains BLOCKED in this environment: Playwright
has no Chromium binary and its attempted browser download returned an invalid
archive. JavaScript syntax and real Node-client/Python-server transport pass;
no browser screenshot, layout pass, Xcode build or physical-glasses pass is claimed.

## Reuse and release gates

Existing native phone capture in draft PR #13 (`405c8495…`) has `CaptureDisk`
original-byte/hash/readback and local Outbox, but no upload adapter. Reuse its
disk boundary when joining SDK media to the v0.3 transport. Do not merge that
draft or change its working phone capture in this spike. Existing P0 Issue #9,
PR #8 filing/storage abstractions and #11 remain separate and unmerged.
The filing synthetic object adapter deliberately admits synthetic documents,
not arbitrary MP4/voice originals; don't bypass that guard for real media.

Railway read-only inventory on 5 November: existing pilot has Postgres and two
test services; **zero private buckets**. No staged changes. Deployment SUCCESS
is not proof of an accepted media vault. No existing secure real-media intake
endpoint was verified. Proposed pilot contract stays PUT/GET `/v1/jobs/{uuid}`
behind TLS, scoped per-user authentication and reviewed private original storage,
with independent size/hash readback. Final hostname, retention, residency,
encryption, backup/restore and credentials belong to Zara/Lindsey review. No
guessed endpoint or token is embedded in the client.

Next smallest physical gate: build a combined DisplayAccess/CameraAccess spike
on an approved Mac/iPhone; obtain explicit approval before signing/installing,
registration or camera/mic grants; show a display button, capture a synthetic
target, lock/put away phone, select Send and confirm original-byte receipt.
Test audio separately before promising all three functions. Local tests and
native view source are not proof this gate passed.

Do not activate Railway, buy anything, change permissions, upload real recordings,
alter the WhatsApp Business number, merge or publish from this prototype.
Rollback: close the draft PR/leave branch unmerged; stop local harness. Existing
app, pilot and database are unchanged. Existing WhatsApp workflow stays a
user-operated fallback only; it does not prove direct SDK permissions or
original-quality transfer.
