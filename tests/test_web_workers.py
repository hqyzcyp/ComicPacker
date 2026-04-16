import queue
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import web_server


class WebWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(dir='/mnt')
        self.root = Path(self.tempdir.name)
        self.input_a = self.root / 'job-a'
        self.input_b = self.root / 'job-b'
        self.output_dir = self.root / 'output'
        self.input_a.mkdir()
        self.input_b.mkdir()
        self.client = web_server.app.test_client()
        self.reset_runtime(worker_count=2)

    def tearDown(self):
        web_server.shutdown_worker_pool()
        web_server.job_queue = queue.Queue()
        with web_server.jobs_lock:
            web_server.jobs.clear()
            web_server.cancelled_jobs.clear()
        with web_server.console_output_lock:
            web_server.console_output.clear()
        self.tempdir.cleanup()

    def reset_runtime(self, worker_count: int):
        web_server.shutdown_worker_pool()
        web_server.job_queue = queue.Queue()
        with web_server.jobs_lock:
            web_server.jobs.clear()
            web_server.cancelled_jobs.clear()
        with web_server.console_output_lock:
            web_server.console_output.clear()
        web_server.start_worker_pool(worker_count=worker_count, force=True)

    def create_job(self, folder: Path, mode: str = 'batch') -> str:
        response = self.client.post(
            '/api/jobs',
            json={
                'folder': str(folder),
                'mode': mode,
                'output': str(self.output_dir),
            }
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        self.assertIn('job_id', payload)
        return payload['job_id']

    def wait_for(self, predicate, timeout: float = 5.0, interval: float = 0.05, message: str = 'condition timed out'):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(interval)
        raise AssertionError(message)

    def get_job(self, job_id: str) -> dict:
        response = self.client.get(f'/api/jobs/{job_id}')
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_jobs_can_run_in_parallel_with_multiple_workers(self):
        self.reset_runtime(worker_count=2)
        started_threads = []
        started_event = threading.Event()
        release_event = threading.Event()
        state_lock = threading.Lock()

        def fake_batch_convert(folder_path, progress_callback=None, **kwargs):
            progress_callback('processing', 1, 1, f'{Path(folder_path).name} running')
            with state_lock:
                started_threads.append(threading.current_thread().name)
                if len(started_threads) >= 2:
                    started_event.set()
            if not started_event.wait(2):
                raise RuntimeError('parallel start timeout')
            release_event.wait(5)
            progress_callback('completed', 1, 1, f'{Path(folder_path).name} done')

        with mock.patch.object(web_server, 'pack_comics_to_pdf_with_progress', side_effect=fake_batch_convert):
            job_a = self.create_job(self.input_a)
            job_b = self.create_job(self.input_b)

            self.wait_for(
                lambda: sum(
                    1 for job_id in (job_a, job_b)
                    if self.get_job(job_id)['status'] == 'running'
                ) == 2,
                message='expected both jobs to reach running state in parallel',
            )

            workers = {self.get_job(job_a)['worker'], self.get_job(job_b)['worker']}
            self.assertEqual(len(workers), 2)

            release_event.set()
            self.wait_for(
                lambda: all(
                    self.get_job(job_id)['status'] == 'completed'
                    for job_id in (job_a, job_b)
                ),
                message='expected both jobs to complete',
            )

    def test_pending_job_can_be_cancelled_while_another_worker_is_busy(self):
        self.reset_runtime(worker_count=1)
        started_folders = []
        release_event = threading.Event()

        def fake_batch_convert(folder_path, progress_callback=None, **kwargs):
            started_folders.append(Path(folder_path).name)
            progress_callback('processing', 1, 1, f'{Path(folder_path).name} running')
            release_event.wait(5)
            progress_callback('completed', 1, 1, f'{Path(folder_path).name} done')

        with mock.patch.object(web_server, 'pack_comics_to_pdf_with_progress', side_effect=fake_batch_convert):
            job_a = self.create_job(self.input_a)
            job_b = self.create_job(self.input_b)

            self.wait_for(
                lambda: self.get_job(job_a)['status'] == 'running' and self.get_job(job_b)['status'] == 'pending',
                message='expected second job to remain pending behind busy single worker',
            )

            cancel_response = self.client.post(f'/api/jobs/{job_b}/cancel')
            self.assertEqual(cancel_response.status_code, 200, cancel_response.get_json())

            release_event.set()

            self.wait_for(
                lambda: self.get_job(job_a)['status'] == 'completed' and self.get_job(job_b)['status'] == 'cancelled',
                message='expected first job to complete and second job to cancel before start',
            )

            self.assertEqual(started_folders, ['job-a'])

    def test_console_output_keeps_job_prefixes_under_parallel_execution(self):
        self.reset_runtime(worker_count=2)
        started_labels = []
        started_event = threading.Event()
        release_event = threading.Event()
        state_lock = threading.Lock()

        def fake_batch_convert(folder_path, progress_callback=None, **kwargs):
            label = Path(folder_path).name
            print(f'{label}: line1')
            progress_callback('processing', 1, 1, f'{label} running')
            with state_lock:
                started_labels.append(label)
                if len(started_labels) >= 2:
                    started_event.set()
            if not started_event.wait(2):
                raise RuntimeError('parallel logging timeout')
            print(f'{label}: line2')
            release_event.wait(5)
            progress_callback('completed', 1, 1, f'{label} done')

        with mock.patch.object(web_server, 'pack_comics_to_pdf_with_progress', side_effect=fake_batch_convert):
            job_a = self.create_job(self.input_a)
            job_b = self.create_job(self.input_b)

            self.wait_for(
                lambda: all(self.get_job(job_id)['status'] == 'running' for job_id in (job_a, job_b)),
                message='expected both jobs running before checking console output',
            )

            release_event.set()
            self.wait_for(
                lambda: all(self.get_job(job_id)['status'] == 'completed' for job_id in (job_a, job_b)),
                message='expected both jobs to complete',
            )

        console_response = self.client.get('/api/console-output')
        self.assertEqual(console_response.status_code, 200, console_response.get_json())
        output_lines = console_response.get_json()['output']

        self.assertTrue(any(job_a[:8] in line and 'job-a: line1' in line for line in output_lines))
        self.assertTrue(any(job_b[:8] in line and 'job-b: line1' in line for line in output_lines))
        self.assertFalse(any(job_a[:8] in line and 'job-b: line' in line for line in output_lines))
        self.assertFalse(any(job_b[:8] in line and 'job-a: line' in line for line in output_lines))


if __name__ == '__main__':
    unittest.main()
