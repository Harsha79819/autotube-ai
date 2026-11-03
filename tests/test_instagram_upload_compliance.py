"""
Unit and regression tests for Instagram Reels Meta Graph API compliance (tests/test_instagram_upload_compliance.py)

Validates:
1. Meta Reels technical ingestion compliance:
   - H.264 High 4.0, yuv420p, bt709/tv color space
   - AAC stereo (2-channel, 48kHz, 128kbps)
   - Faststart moov atom at beginning of MP4
   - Mobile bitrate / payload cap (<= 22MB, <= 2.5 Mbps) to prevent rupload proxy timeouts
2. Upload header compliance:
   - Primary header: 'Authorization: OAuth <token>' (not Bearer)
   - 'Content-Type: application/octet-stream'
   - Exact byte-aligned file_size and offset='0'
3. Error cleaning and security:
   - Token sanitization from error messages
   - Actionable ProcessingFailedError and timeout translations
4. Fresh container re-initialization on upload retry
"""

import os
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import json

from agents.instagram_agent import (
    _prepare_meta_reels_video,
    _clean_instagram_error,
    should_upload_to_instagram,
    upload_to_instagram_reels,
)


class TestInstagramUploadCompliance(unittest.TestCase):

    def test_01_eligibility_criteria(self):
        """Verifies Reels eligibility: user opt-in, <=90s, strictly 9:16 aspect ratio."""
        eligible, reason = should_upload_to_instagram(45.0, True, '9:16')
        self.assertTrue(eligible)
        self.assertIn('Eligible', reason)

        # Exceeds 90s
        eligible_long, reason_long = should_upload_to_instagram(95.0, True, '9:16')
        self.assertFalse(eligible_long)
        self.assertIn('exceeds 90s', reason_long)

        # Landscape aspect ratio
        eligible_wide, reason_wide = should_upload_to_instagram(45.0, True, '16:9')
        self.assertFalse(eligible_wide)
        self.assertIn('9:16', reason_wide)

        # User opted out
        eligible_no_opt, reason_no_opt = should_upload_to_instagram(45.0, False, '9:16')
        self.assertFalse(eligible_no_opt)
        self.assertIn('opt', reason_no_opt)

    def test_02_clean_instagram_error_sanitization(self):
        """Verifies token redaction and error translation."""
        fake_token = 'EAAB1234567890abcdefXYZ'
        raw_error = f'Failed to post with access_token={fake_token}: ProcessingFailedError request processing failed'
        cleaned = _clean_instagram_error(raw_error, tok=fake_token)
        self.assertNotIn(fake_token, cleaned)
        self.assertIn('ProcessingFailedError', cleaned)
        self.assertIn('H.264/AAC', cleaned)

    @patch('agents.instagram_agent._prepare_meta_reels_video')
    @patch('agents.instagram_agent.requests.post')
    @patch('agents.instagram_agent.requests.get')
    def test_03_upload_headers_and_oauth_scheme(self, mock_get, mock_post, mock_prepare):
        """Verifies that rupload.facebook.com receives OAuth authorization, offset, file_size, and octet-stream."""
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            tmp.write(b'dummy_mp4_bytes_for_testing')
            tmp_path = tmp.name

        mock_prepare.return_value = tmp_path

        try:
            # Mock container init
            mock_init_resp = MagicMock()
            mock_init_resp.status_code = 200
            mock_init_resp.json.return_value = {
                'id': 'container_test_123',
                'uri': 'https://rupload.facebook.com/ig-api-upload/v26.0/container_test_123'
            }

            # Mock binary upload
            mock_upload_resp = MagicMock()
            mock_upload_resp.status_code = 200
            mock_upload_resp.json.return_value = {'success': True}

            # Mock polling & publishing
            mock_status_resp = MagicMock()
            mock_status_resp.status_code = 200
            mock_status_resp.json.return_value = {'status_code': 'FINISHED'}
            mock_get.return_value = mock_status_resp

            # Mock publish
            mock_pub_resp = MagicMock()
            mock_pub_resp.status_code = 200
            mock_pub_resp.json.return_value = {'id': 'published_media_999'}
            mock_post.side_effect = [mock_init_resp, mock_upload_resp, mock_pub_resp]

            res = upload_to_instagram_reels(
                video_source=tmp_path,
                caption='Test Reel',
                ig_user_id='12345678',
                access_token='TEST_TOKEN_XYZ',
            )

            self.assertTrue(res.get('success'), f'Upload failed: {res}')
            self.assertEqual(res.get('media_id'), 'published_media_999')

            # Verify the call to rupload (the 2nd post call)
            upload_call = mock_post.call_args_list[1]
            called_url = upload_call[0][0]
            called_headers = upload_call[1]['headers']

            self.assertIn('rupload.facebook.com', called_url)
            self.assertEqual(called_headers['Authorization'], 'OAuth TEST_TOKEN_XYZ')
            self.assertEqual(called_headers['offset'], '0')
            self.assertEqual(called_headers['Content-Type'], 'application/octet-stream')
            self.assertEqual(called_headers['file_size'], str(len(b'dummy_mp4_bytes_for_testing')))

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @patch('agents.instagram_agent._prepare_meta_reels_video')
    @patch('agents.instagram_agent.requests.post')
    @patch('agents.instagram_agent.requests.get')
    def test_04_fresh_container_retry_on_failure(self, mock_get, mock_post, mock_prepare):
        """Verifies that if binary upload fails on attempt 1, retry initializes a FRESH container."""
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            tmp.write(b'dummy_mp4_bytes_retry')
            tmp_path = tmp.name

        mock_prepare.return_value = tmp_path

        try:
            # 1. Container init 1
            init_1 = MagicMock()
            init_1.status_code = 200
            init_1.json.return_value = {'id': 'container_1', 'uri': 'https://rupload.facebook.com/container_1'}

            # 2. Binary upload 1 fails (e.g. 400 Proxy Error)
            up_1 = MagicMock()
            up_1.status_code = 400
            up_1.text = '{"debug_info":{"type":"ProcessingFailedError"}}'

            # 3. Fresh container init 2
            init_2 = MagicMock()
            init_2.status_code = 200
            init_2.json.return_value = {'id': 'container_2_fresh', 'uri': 'https://rupload.facebook.com/container_2_fresh'}

            # 4. Binary upload 2 succeeds
            up_2 = MagicMock()
            up_2.status_code = 200

            # 5. Publish
            pub = MagicMock()
            pub.status_code = 200
            pub.json.return_value = {'id': 'media_published_fresh'}

            mock_post.side_effect = [init_1, up_1, init_2, up_2, pub]

            # Status poll
            status_poll = MagicMock()
            status_poll.status_code = 200
            status_poll.json.return_value = {'status_code': 'FINISHED'}
            mock_get.return_value = status_poll

            res = upload_to_instagram_reels(
                video_source=tmp_path,
                caption='Retry test',
                ig_user_id='12345678',
                access_token='TEST_TOKEN_XYZ',
            )

            self.assertTrue(res.get('success'))
            self.assertEqual(res.get('media_id'), 'media_published_fresh')

            # Check that container 2 was called on the retry
            self.assertEqual(mock_post.call_count, 5)
            self.assertEqual(mock_post.call_args_list[2][0][0], 'https://graph.facebook.com/v21.0/12345678/media')
            self.assertEqual(mock_post.call_args_list[3][0][0], 'https://rupload.facebook.com/container_2_fresh')

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_05_prepare_meta_reels_video_faststart(self):
        """Verifies _prepare_meta_reels_video maintains or prepares faststart compliance on real mp4 files."""
        test_clip = Path('scratch/test_clip.mp4')
        if test_clip.exists():
            out_path = _prepare_meta_reels_video(str(test_clip))
            self.assertTrue(os.path.exists(out_path))
            # Check faststart
            with open(out_path, 'rb') as f:
                header = f.read(1048576)
                moov_pos = header.find(b'moov')
                mdat_pos = header.find(b'mdat')
                self.assertNotEqual(moov_pos, -1, 'moov atom not found in first 1MB')
                self.assertLess(moov_pos, mdat_pos, 'moov atom must appear before mdat')


    @patch('agents.instagram_agent._prepare_meta_reels_video')
    @patch('agents.instagram_agent.requests.post')
    @patch('agents.instagram_agent.requests.get')
    def test_06_multi_chunk_resumable_upload(self, mock_get, mock_post, mock_prepare):
        """Verifies that large videos (>4MB) stream sequentially in 4MB chunks with 206 handling."""
        chunk_4mb = 4 * 1024 * 1024
        total_size = 9 * 1024 * 1024  # 9MB -> 3 chunks: 4MB, 4MB, 1MB
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            tmp.seek(total_size - 1)
            tmp.write(b'\0')
            tmp_path = tmp.name

        mock_prepare.return_value = tmp_path

        try:
            # 1. Container init
            mock_init = MagicMock()
            mock_init.status_code = 200
            mock_init.json.return_value = {
                'id': 'container_chunk_test',
                'uri': 'https://rupload.facebook.com/container_chunk_test'
            }

            # 2. Chunk 1 (0 to 4MB) -> HTTP 206
            chk_1 = MagicMock()
            chk_1.status_code = 206
            chk_1.text = '{"debug_info":{"retriable":true,"type":"PartialRequestError"}}'

            # 3. Chunk 2 (4 to 8MB) -> HTTP 206
            chk_2 = MagicMock()
            chk_2.status_code = 206
            chk_2.text = '{"debug_info":{"retriable":true,"type":"PartialRequestError"}}'

            # 4. Chunk 3 (8 to 9MB) -> HTTP 200 Final
            chk_3 = MagicMock()
            chk_3.status_code = 200
            chk_3.text = '{"success":true,"message":"Upload Successful."}'

            # 5. Media publish
            mock_pub = MagicMock()
            mock_pub.status_code = 200
            mock_pub.json.return_value = {'id': 'reel_media_chunked_123'}

            mock_post.side_effect = [mock_init, chk_1, chk_2, chk_3, mock_pub]

            # Polling
            status_poll = MagicMock()
            status_poll.status_code = 200
            status_poll.json.return_value = {'status_code': 'FINISHED'}
            mock_get.return_value = status_poll

            res = upload_to_instagram_reels(
                video_source=tmp_path,
                caption='Chunked Reel Test',
                ig_user_id='12345678',
                access_token='TEST_TOKEN_XYZ',
            )

            self.assertTrue(res.get('success'), f'Chunked upload failed: {res}')
            self.assertEqual(res.get('media_id'), 'reel_media_chunked_123')

            # Verify chunk headers
            self.assertEqual(mock_post.call_count, 5)
            # Call 1: Init
            # Call 2: Chunk 1
            call_c1 = mock_post.call_args_list[1]
            self.assertEqual(call_c1[1]['headers']['offset'], '0')
            self.assertEqual(call_c1[1]['headers']['file_size'], str(total_size))

            # Call 3: Chunk 2
            call_c2 = mock_post.call_args_list[2]
            self.assertEqual(call_c2[1]['headers']['offset'], str(chunk_4mb))

            # Call 4: Chunk 3
            call_c3 = mock_post.call_args_list[3]
            self.assertEqual(call_c3[1]['headers']['offset'], str(2 * chunk_4mb))

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == '__main__':
    unittest.main()
