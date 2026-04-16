import queue
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import web_server


class WebUiApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(dir='/mnt')
        self.root = Path(self.tempdir.name)
        self.client = web_server.app.test_client()
        self.reset_runtime()

    def tearDown(self):
        web_server.shutdown_worker_pool()
        web_server.job_queue = queue.Queue()
        with web_server.jobs_lock:
            web_server.jobs.clear()
            web_server.cancelled_jobs.clear()
        with web_server.console_output_lock:
            web_server.console_output.clear()
        self.tempdir.cleanup()

    def reset_runtime(self):
        web_server.shutdown_worker_pool()
        web_server.job_queue = queue.Queue()
        with web_server.jobs_lock:
            web_server.jobs.clear()
            web_server.cancelled_jobs.clear()
        with web_server.console_output_lock:
            web_server.console_output.clear()

    def test_detect_mode_returns_ui_analysis_contract(self):
        folder = self.root / '[相反的你和我][阿賀沢紅茶][Vol.01-Vol.08]'
        folder.mkdir()
        (folder / 'Vol.01.cbz').write_bytes(b'cbz')

        response = self.client.post('/api/detect-mode', json={'path': str(folder)})
        self.assertEqual(response.status_code, 200, response.get_json())

        payload = response.get_json()
        self.assertEqual(payload['recommended_mode'], 'cbz')
        self.assertEqual(payload['first_file_name'], 'Vol.01.cbz')
        self.assertEqual(payload['comic_name'], '相反的你和我')
        self.assertEqual(payload['output_preview'], '相反的你和我 Vol.01')
        self.assertEqual(payload['naming_source'], 'folder')
        self.assertEqual(payload['naming_confidence'], 'medium')
        self.assertTrue(payload['has_vol_files'])
        self.assertEqual(payload['vol_files_count'], 1)
        self.assertEqual(payload['total_comic_files'], 1)

    def test_create_job_rejects_unsupported_mode(self):
        folder = self.root / 'unsupported-mode-job'
        folder.mkdir()
        output_dir = self.root / 'output'

        response = self.client.post(
            '/api/jobs',
            json={
                'folder': str(folder),
                'mode': 'unsupported-mode',
                'output': str(output_dir),
            },
        )

        self.assertEqual(response.status_code, 400, response.get_json())
        payload = response.get_json()
        self.assertIn('不支持的模式', payload['error'])

        with web_server.jobs_lock:
            self.assertEqual(web_server.jobs, {})

    def test_clear_jobs_reports_correct_removed_count(self):
        with web_server.jobs_lock:
            web_server.jobs.update(
                {
                    'completed-job': {'id': 'completed-job', 'status': 'completed', 'created_time': '2026-04-16T12:00:00'},
                    'failed-job': {'id': 'failed-job', 'status': 'failed', 'created_time': '2026-04-16T12:01:00'},
                    'cancelled-job': {'id': 'cancelled-job', 'status': 'cancelled', 'created_time': '2026-04-16T12:02:00'},
                    'running-job': {'id': 'running-job', 'status': 'running', 'created_time': '2026-04-16T12:03:00'},
                    'pending-job': {'id': 'pending-job', 'status': 'pending', 'created_time': '2026-04-16T12:04:00'},
                }
            )

        response = self.client.post('/api/jobs/clear')
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()

        self.assertTrue(payload['success'])
        self.assertEqual(payload['message'], '已清除 3 条历史记录')

        jobs_response = self.client.get('/api/jobs')
        remaining_ids = [job['id'] for job in jobs_response.get_json()['jobs']]
        self.assertEqual(set(remaining_ids), {'running-job', 'pending-job'})

    def test_create_job_forces_keep_pdf_when_mobi_disabled(self):
        folder = self.root / 'pdf-retention-default'
        folder.mkdir()
        output_dir = self.root / 'output'

        response = self.client.post(
            '/api/jobs',
            json={
                'folder': str(folder),
                'mode': 'book',
                'output': str(output_dir),
                'convert_to_mobi': False,
                'keep_pdf': False,
            },
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        job_id = response.get_json()['job_id']

        with web_server.jobs_lock:
            params = web_server.jobs[job_id]['parameters']

        self.assertFalse(params['convert_to_mobi'])
        self.assertTrue(params['keep_pdf'])

    def test_create_job_allows_keep_pdf_false_when_mobi_enabled(self):
        folder = self.root / 'pdf-retention-disabled'
        folder.mkdir()
        output_dir = self.root / 'output'

        response = self.client.post(
            '/api/jobs',
            json={
                'folder': str(folder),
                'mode': 'cbz',
                'output': str(output_dir),
                'convert_to_mobi': True,
                'keep_pdf': False,
            },
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        job_id = response.get_json()['job_id']

        with web_server.jobs_lock:
            params = web_server.jobs[job_id]['parameters']

        self.assertTrue(params['convert_to_mobi'])
        self.assertFalse(params['keep_pdf'])


if __name__ == '__main__':
    unittest.main()
