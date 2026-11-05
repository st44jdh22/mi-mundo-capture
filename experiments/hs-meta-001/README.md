# HS-META-001 | Hey Sophie Meta Display capture feasibility

**Status: TESTED LOCALLY FOR SYNTHETIC UI/CONTRACT ONLY. NOT INSTALLED, HOSTED OR GLASSES-TESTED.**

Original commission: https://docs.google.com/document/d/1iUOvvSCEFKfQPrfdRdI4BOaNJep5z2eFmoKlt8an44M/edit
Development issue: https://github.com/st44jdh22/mi-mundo-capture/issues/14

## Platform facts and limitations

Meta supports on-glasses Web Apps (HTML/JS, D-pad/Neural Band navigation) and native iOS/Android Device Access Toolkit (DAT) extensions with Ray-Ban Display UI and camera/audio APIs. The Meta iOS CameraAccess sample demonstrates taking photos and recording video, optionally using the glasses' microphone for video sound. Standalone microphone PCM/audio and standalone high-quality photo APIs have experimental/release limitations in Meta's public SDK README. Glasses Web App camera/microphone access is **not established**; a Web App preview cannot stand in for actual capture. The native iOS sample stops an active session when backgrounded. A working no-phone-handling journey and custom shortcut remain **unverified**. WhatsApp's observed 15-second direct-send limit is not an SDK limit.

Official references:
- https://developers.meta.com/wearables/faq/
- https://developers.meta.com/wearables/device-access-toolkit/
- https://developers.meta.com/wearables/web-apps/
- https://github.com/meta/meta-wearables-dat-ios/tree/main/samples/CameraAccess
- https://github.com/meta/meta-wearables-dat-ios
- https://github.com/meta/meta-wearables-webapp

## Contents

- experiments/hs-meta-001/index.html: 600 x 600 PHOTO, VIDEO, AUDIO and SEND preview with keyboard arrows + Enter to simulate Neural Band. No media capture or network.
- experiments/hs-meta-001/controller.mjs: testable state machine, retains unsent capture, refuses success without independently verified test receipt.
- experiments/hs-meta-001/controller.test.mjs: 8 Node tests for no SDK, no input, uncertain upload, preserved original and receipt conditions.
- integration/test_hs_meta.py: 4 Python tests against the EXISTING Mi Mundo ZIP validator and temporary FixtureStore using *non-playable synthetic marker bytes*, not personal media.
- The existing temporary loopback-only receiver, JavaScript capture client, Post Office and backend are unchanged. This is not a new source of truth or production upload.

Local commands from repository root:

    node --test experiments/hs-meta-001/controller.test.mjs
    python3 -m unittest discover -s integration -p 'test_hs_meta.py' -v

Open index.html via a local HTTP static server to test the display-sized navigation. The preview deliberately blocks capture and Send when no native bridge exists. Do not display RECEIVED when the real destination was not independently read back.

## Smallest practical next milestone

Build on existing native Hey Sophie iPhone draft PR #13 (review/heysophie-native-iphone-v01), adding Meta Wearables DAT and its official CameraAccess flow. First test paired glasses plus iPhone in an authorised isolated environment for display/Neural Band navigation, PHOTO, VIDEO with sound and standalone AUDIO, independently marking each mode PASS or BLOCKED. Confirm background/foreground conditions and whether a phone companion can stay untouched. Add an immutable local original outbox and existing v0.3 ZIP export; connect a synthetic transfer to the current Mi Mundo receipt/readback contract only after an approved private test endpoint is available. No duplicate backend.

Railway remains under a security hold; no access or deployment. No production changes, external communication, real media, publishing, Meta/Apple credential changes, new service activation or expenditure are authorised.

**Physical glasses app, signed iPhone app, secure hosted receiver and successful no-touch transfer are NOT VERIFIED.**
