"""All media, identities, scopes and destinations are fabricated. No network."""
import dataclasses
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bird_synthetic import (JPEG, JPEG_SHA256, NOW, STAGES, Blocked, MockBird, MockWork,
                            Pipeline, Selection, digest, event, signed, unpack)


class BirdSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bird = MockBird()
        self.work = MockWork(self.root / 'work')
        self.pipeline = Pipeline(self.root / 'outbox', self.bird, self.work)
        for target in ('socket.socket.connect', 'socket.create_connection', 'urllib.request.urlopen'):
            blocker = patch(target, side_effect=AssertionError('Network forbidden in Bird synthetic tests'))
            blocker.start()
            self.addCleanup(blocker.stop)

    def run_event(self, payload=None, pipeline=None):
        return (pipeline or self.pipeline).run(*signed(payload or event()))

    def original(self, result):
        return self.root / 'outbox' / result['job_id'] / 'original.zip'

    def test_full_path_original_bytes_and_independent_receipt(self):
        result = self.run_event()
        self.assertEqual(result['status'], 'INDEPENDENTLY_VERIFIED')
        self.assertEqual(result['history'], list(STAGES))
        self.assertEqual(result['label'], 'NOT LIVE')
        self.assertFalse(result['live_provider_verified'])
        self.assertFalse(result['production_routed'])
        manifest, photo = unpack(self.original(result).read_bytes())
        self.assertEqual(photo, JPEG.read_bytes())
        self.assertEqual(digest(photo), JPEG_SHA256)
        self.assertEqual(manifest['attachments'][0]['bytes'], 742)
        self.assertEqual(manifest['attachments'][0]['content_type'], 'image/jpeg')
        self.assertEqual(manifest['source']['correlation'], result['correlation'])
        receipt = self.work.lookup(result['job_id'])
        self.assertEqual(receipt['receipt_id'], result['receipt_id'])
        self.assertEqual(self.work.readback(result['job_id']), self.original(result).read_bytes())

    def test_wrong_sender_workspace_recipient_and_subscription_before_fetch(self):
        for field, value in (('workspace_id', 'other-workspace'), ('from', {'bsuid': 'other-sender'}),
                             ('to', 'other-recipient'), ('direction', 'outbound')):
            with self.subTest(field=field):
                payload = event()
                payload['data'][field] = value
                self.assertEqual(self.run_event(payload)['status'], 'BLOCKED')
        body, headers = signed(event())
        headers['X-MCP-Subscription-Id'] = 'wrong-subscription'
        self.assertEqual(self.pipeline.run(body, headers)['status'], 'BLOCKED')
        self.assertEqual(self.bird.calls, 0)
        self.assertFalse((self.root / 'outbox').exists())

    def test_each_missing_scope_is_a_genuine_preflight_denial(self):
        for scope in ('whatsapp:read', 'webhooks:write'):
            selection = dataclasses.replace(Selection(), scopes=Selection().scopes - {scope})
            result = self.run_event(pipeline=Pipeline(self.root / 'outbox', self.bird, self.work, selection))
            self.assertEqual(result['reason'], 'UNAUTHORISED_SCOPE')
            self.assertIsNone(result['stage'])
        self.assertEqual(self.bird.calls, 0)
        self.assertEqual(self.work.deliveries, 0)

    def test_signature_replay_size_and_invalid_envelope(self):
        body, headers = signed(event())
        self.assertEqual(self.pipeline.run(body + b' ', headers)['status'], 'BLOCKED')
        self.assertEqual(self.pipeline.run(*signed(event(), NOW - 301))['status'], 'BLOCKED')
        self.assertEqual(self.pipeline.run(*signed(event(), NOW + 301))['status'], 'BLOCKED')
        self.assertEqual(self.pipeline.run(b'x' * (256 * 1024 + 1), headers)['reason'], 'EVENT_TOO_LARGE')
        payload = event()
        payload['data']['audio'] = {'id': 'extra-content-arm'}
        self.assertEqual(self.run_event(payload)['status'], 'BLOCKED')
        self.assertEqual(self.pipeline.run(*signed({'eventId': 'malformed'}))['status'], 'BLOCKED')
        self.assertEqual(self.bird.calls, 0)

    def test_missing_and_expired_media_have_distinct_blocked_reasons(self):
        for code in ('MEDIA_NOT_FOUND_404', 'MEDIA_GONE_410'):
            with self.subTest(code=code):
                self.bird.failure = Blocked(code)
                result = self.run_event()
                self.assertEqual(result['status'], 'BLOCKED')
                self.assertEqual(result['reason'], code)
                self.assertEqual(result['stage'], 'EVENT_RECEIVED')
                self.assertFalse(self.original(result).exists())
        self.assertEqual(self.work.deliveries, 0)

    def test_empty_wrong_mime_length_changed_bytes_and_media_correlation(self):
        good = self.bird.fetch('synthetic-workspace', 'synthetic-message-1', 'synthetic-media-1')
        changes = ({'data': b'', 'content_length': 0}, {'content_type': 'image/png'},
                   {'content_length': 1}, {'data': good.data[:-1] + b'x'},
                   {'message_id': 'other-message'}, {'workspace': 'other-workspace'},
                   {'media_id': 'other-media'})
        for change in changes:
            with self.subTest(change=list(change)):
                with patch.object(self.bird, 'fetch', return_value=dataclasses.replace(good, **change)):
                    # Independent outboxes ensure every invalid fetch is actually exercised.
                    pipeline = Pipeline(self.root / ('case-' + str(changes.index(change))), self.bird, self.work)
                    result = self.run_event(pipeline=pipeline)
                    self.assertEqual(result['status'], 'BLOCKED')
                    self.assertEqual(result['stage'], 'EVENT_RECEIVED')
        self.assertEqual(self.work.deliveries, 0)

    def test_duplicate_and_new_event_for_same_media_fetch_and_deliver_once(self):
        first = self.run_event()
        repeated = self.run_event()
        alias = self.run_event(event(event_id='synthetic-event-alias'))
        self.assertEqual(first['job_id'], alias['job_id'])
        self.assertEqual(first['receipt_id'], repeated['receipt_id'])
        self.assertEqual(alias['status'], 'INDEPENDENTLY_VERIFIED')
        self.assertEqual(len(alias['events']), 2)
        self.assertEqual(self.bird.calls, 1)
        self.assertEqual(self.work.deliveries, 1)

    def test_event_id_changed_body_conflict_preserves_original_and_history(self):
        first = self.run_event()
        original = self.original(first).read_bytes()
        changed = event()
        changed['data']['image']['caption'] = 'changed replay'
        conflict = self.run_event(changed)
        self.assertEqual(conflict['reason'], 'EVENT_ID_CONTENT_CONFLICT')
        self.assertEqual(conflict['history'], list(STAGES))
        self.assertEqual(self.original(first).read_bytes(), original)
        cross_message = self.run_event(event(message_id='another-message'))
        self.assertEqual(cross_message['reason'], 'EVENT_ID_CONTENT_CONFLICT')
        self.assertEqual(self.work.deliveries, 1)

    def test_out_of_order_distinct_messages_are_not_dropped(self):
        later = self.run_event(event('later', 'message-later', NOW))
        earlier = self.run_event(event('earlier', 'message-earlier', NOW - 3600))
        self.assertNotEqual(later['job_id'], earlier['job_id'])
        self.assertEqual(earlier['status'], 'INDEPENDENTLY_VERIFIED')
        self.assertEqual(self.work.deliveries, 2)

    def test_failed_delivery_keeps_original_then_restart_retries_without_refetch(self):
        self.work.failure = 'delivery'
        failed = self.run_event()
        self.assertEqual(failed['status'], 'FAILED')
        self.assertEqual(failed['stage'], 'MEDIA_FETCHED')
        original = self.original(failed).read_bytes()
        bird = MockBird(Blocked('MUST_NOT_REFETCH'))
        recovered = self.run_event(pipeline=Pipeline(self.root / 'outbox', bird, MockWork(self.root / 'work')))
        self.assertEqual(recovered['status'], 'INDEPENDENTLY_VERIFIED')
        self.assertEqual(recovered['job_id'], failed['job_id'])
        self.assertEqual(self.original(recovered).read_bytes(), original)
        self.assertEqual(bird.calls, 0)

    def test_lost_ack_is_reconciled_without_resending(self):
        self.work.failure = 'lost_ack'
        result = self.run_event()
        self.assertEqual(result['status'], 'INDEPENDENTLY_VERIFIED')
        self.assertEqual(self.work.deliveries, 1)
        self.assertEqual(self.run_event()['receipt_id'], result['receipt_id'])
        self.assertEqual(self.work.deliveries, 1)

    def test_lost_ack_and_lost_lookup_recover_in_new_instances_without_resend(self):
        self.work.failure = 'lost_ack'
        with patch.object(self.work, 'lookup', side_effect=[None, OSError('lookup unavailable')]):
            failed = self.run_event()
        self.assertEqual(failed['status'], 'FAILED')
        self.assertEqual(failed['stage'], 'MEDIA_FETCHED')
        restarted_work = MockWork(self.root / 'work')
        restarted_bird = MockBird(Blocked('MUST_NOT_REFETCH'))
        recovered = self.run_event(pipeline=Pipeline(self.root / 'outbox', restarted_bird, restarted_work))
        self.assertEqual(recovered['status'], 'INDEPENDENTLY_VERIFIED')
        self.assertEqual(restarted_work.deliveries, 0)
        self.assertEqual(restarted_bird.calls, 0)

    def test_interruption_after_package_before_media_stage_recovers_original(self):
        with patch.object(self.pipeline, 'advance', side_effect=SystemExit('simulated abrupt termination')):
            with self.assertRaises(SystemExit):
                self.run_event()
        packages = list((self.root / 'outbox').glob('*/original.zip'))
        self.assertEqual(len(packages), 1)
        original = packages[0].read_bytes()
        restarted_bird = MockBird(Blocked('MUST_NOT_REFETCH'))
        recovered = self.run_event(pipeline=Pipeline(self.root / 'outbox', restarted_bird, self.work))
        self.assertEqual(recovered['status'], 'INDEPENDENTLY_VERIFIED')
        self.assertEqual(packages[0].read_bytes(), original)
        self.assertEqual(restarted_bird.calls, 0)

    def test_destination_acceptance_is_not_independent_verification(self):
        self.work.failure = 'readback'
        failed = self.run_event()
        self.assertEqual(failed['status'], 'FAILED')
        self.assertEqual(failed['stage'], 'DESTINATION_ACCEPTED')
        self.assertNotIn('INDEPENDENTLY_VERIFIED', failed['history'])
        self.work.failure = None
        self.assertEqual(self.run_event()['status'], 'INDEPENDENTLY_VERIFIED')
        self.assertEqual(self.work.deliveries, 1)

    def test_wrong_receipt_cannot_produce_success(self):
        first = self.run_event()
        good = self.work.lookup(first['job_id'])
        for change in ({'job_id': 'wrong'}, {'receipt_id': 'wrong'}, {'routed': True},
                       {'status': 'RECEIVED'}, {'attachments': 0}, {'package_sha256': '0' * 64}):
            with self.subTest(change=change):
                with patch.object(self.work, 'lookup', return_value={**good, **change}):
                    result = self.run_event()
                    self.assertEqual(result['reason'], 'DESTINATION_RECEIPT_MISMATCH')
                    self.assertEqual(result['status'], 'BLOCKED')

    def test_different_independent_bytes_cannot_produce_success(self):
        first = self.run_event()
        changed = self.work.readback(first['job_id']) + b'changed ZIP bytes'
        with patch.object(self.work, 'readback', return_value=changed):
            result = self.run_event()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['reason'], 'DESTINATION_READBACK_MISMATCH')

    def test_corrupt_original_never_refetched_or_overwritten(self):
        first = self.run_event()
        path = self.original(first)
        path.write_bytes(b'corrupt preserved for diagnosis')
        failed = self.run_event()
        self.assertEqual(failed['status'], 'FAILED')
        self.assertEqual(path.read_bytes(), b'corrupt preserved for diagnosis')
        self.assertEqual(self.bird.calls, 1)

    def test_corrupt_destination_never_returns_cached_success(self):
        first = self.run_event()
        target = self.work.store.root / first['job_id'] / 'original.zip'
        target.write_bytes(b'corrupt remote fixture')
        self.assertEqual(self.run_event()['status'], 'FAILED')
        self.assertEqual(unpack(self.original(first).read_bytes())[1], JPEG.read_bytes())
        self.assertEqual(self.work.deliveries, 1)

    def test_retry_limit_preserves_original_and_prevents_unbounded_delivery(self):
        self.work.failure = 'delivery'
        results = [self.run_event() for _ in range(4)]
        self.assertEqual(results[-1]['reason'], 'RETRY_LIMIT')
        self.assertEqual(self.work.deliveries, 3)
        self.assertTrue(self.original(results[-1]).is_file())

    def test_real_process_restart_keeps_identity_bytes_source_hash_and_receipt(self):
        # Child processes independently reopen disk; no in-memory mock is shared.
        directory = self.root / 'process'
        script = Path(__file__).with_name('bird_synthetic.py')
        bootstrap = """import runpy, sys
from unittest.mock import patch
script = sys.argv.pop(1)
with patch('socket.socket.connect', side_effect=AssertionError('No network')), \\
     patch('socket.create_connection', side_effect=AssertionError('No network')), \\
     patch('urllib.request.urlopen', side_effect=AssertionError('No network')):
    runpy.run_path(script, run_name='__main__')
"""
        command = [sys.executable, '-B', '-c', bootstrap, str(script), '--state', str(directory)]
        failed = subprocess.run(command + ['--mock-failure', 'readback'], capture_output=True, text=True, timeout=10)
        self.assertEqual(failed.returncode, 1, failed.stderr)
        before = json.loads(failed.stdout)
        original = directory / 'outbox' / before['job_id'] / 'original.zip'
        original_bytes = original.read_bytes()
        receipt_bytes = (directory / 'work-mock' / before['job_id'] / 'receipt.json').read_bytes()
        for _ in range(2):
            child = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(child.returncode, 0, child.stderr)
            after = json.loads(child.stdout)
            self.assertEqual(after['status'], 'INDEPENDENTLY_VERIFIED')
            for key in ('job_id', 'receipt_id', 'correlation', 'media_sha256', 'package_sha256'):
                self.assertEqual(after[key], before[key])
            self.assertEqual(original.read_bytes(), original_bytes)
            self.assertEqual((directory / 'work-mock' / after['job_id'] / 'receipt.json').read_bytes(), receipt_bytes)
        self.assertEqual(digest(unpack(original_bytes)[1]), JPEG_SHA256)


if __name__ == '__main__':
    unittest.main()
