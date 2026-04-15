import io
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


def build_jpeg_bytes(size=(1000, 1500), color=(128, 160, 192)) -> bytes:
    image = Image.new('RGB', size, color)
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=90)
    return buffer.getvalue()


def write_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, 'w') as zf:
        for name, data in files.items():
            zf.writestr(name, data)


def get_pdf_page_count(pdf_path: Path) -> int:
    result = subprocess.run(
        ['pdfinfo', str(pdf_path)],
        capture_output=True,
        text=True,
        check=True
    )
    match = re.search(r'^Pages:\s+(\d+)\s*$', result.stdout, re.MULTILINE)
    if not match:
        raise AssertionError(f'Unable to parse page count from pdfinfo output:\n{result.stdout}')
    return int(match.group(1))


@unittest.skipUnless(shutil.which('pdfinfo'), 'pdfinfo is required for PDF workflow tests')
class PdfWorkflowTests(unittest.TestCase):
    def test_batch_mode_generates_expected_page_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / 'input'
            out_dir = root / 'out'
            input_dir.mkdir()

            write_zip(
                input_dir / 'CH-001.zip',
                {
                    '001.jpg': build_jpeg_bytes(color=(255, 0, 0)),
                    '002.jpg': build_jpeg_bytes(color=(0, 255, 0)),
                    '003.jpg': build_jpeg_bytes(color=(0, 0, 255)),
                }
            )

            main.pack_comics_to_pdf(
                str(input_dir),
                batch_size=1,
                pdf_prefix='测试漫画',
                output_folder=str(out_dir),
                comic_name='测试漫画'
            )

            pdf_files = sorted(out_dir.rglob('*.pdf'))
            self.assertEqual(len(pdf_files), 1)
            self.assertEqual(get_pdf_page_count(pdf_files[0]), 3)

    def test_book_mode_generates_expected_page_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / 'input'
            out_dir = root / 'out'
            input_dir.mkdir()

            write_zip(
                input_dir / 'Vol.01.zip',
                {
                    'chapter1/001.jpg': build_jpeg_bytes(color=(255, 0, 0)),
                    'chapter1/002.jpg': build_jpeg_bytes(color=(0, 255, 0)),
                    'chapter2/001.jpg': build_jpeg_bytes(color=(0, 0, 255)),
                    'chapter2/002.jpg': build_jpeg_bytes(color=(255, 255, 0)),
                }
            )

            main.pack_comics_by_book(
                str(input_dir),
                output_folder=str(out_dir),
                comic_name='测试漫画'
            )

            pdf_files = sorted(out_dir.rglob('*.pdf'))
            self.assertEqual(len(pdf_files), 1)
            self.assertEqual(get_pdf_page_count(pdf_files[0]), 4)

    def test_cbz_mode_generates_expected_page_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / 'input'
            out_dir = root / 'out'
            input_dir.mkdir()

            write_zip(
                input_dir / 'Vol.01.cbz',
                {
                    'chapter1/001.jpg': build_jpeg_bytes(color=(255, 0, 0)),
                    'chapter1/002.jpg': build_jpeg_bytes(color=(0, 255, 0)),
                    'chapter2/001.jpg': build_jpeg_bytes(color=(0, 0, 255)),
                    'chapter2/002.jpg': build_jpeg_bytes(color=(255, 255, 0)),
                }
            )

            main.convert_cbz_to_pdf(
                str(input_dir),
                output_folder=str(out_dir),
                comic_name='测试漫画'
            )

            pdf_files = sorted(out_dir.rglob('*.pdf'))
            self.assertEqual(len(pdf_files), 1)
            self.assertEqual(get_pdf_page_count(pdf_files[0]), 4)


if __name__ == '__main__':
    unittest.main()
