import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

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


class OutputRetentionTests(unittest.TestCase):
    def test_batch_mode_removes_pdf_directory_when_keep_pdf_disabled(self):
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
                }
            )

            def fake_convert(pdf_path, mobi_output_dir, kindle_profile):
                mobi_path = Path(mobi_output_dir) / f'{Path(pdf_path).stem}.mobi'
                mobi_path.write_bytes(b'mobi')
                return str(mobi_path)

            with mock.patch.object(main, 'convert_pdf_to_mobi', side_effect=fake_convert):
                main.pack_comics_to_pdf(
                    str(input_dir),
                    batch_size=1,
                    pdf_prefix='测试漫画',
                    output_folder=str(out_dir),
                    convert_to_mobi=True,
                    comic_name='测试漫画',
                    keep_pdf=False
                )

            comic_dir = out_dir / '测试漫画'
            self.assertFalse((comic_dir / 'pdf').exists())
            self.assertTrue((comic_dir / 'mobi').is_dir())
            self.assertEqual(sorted(path.name for path in (comic_dir / 'mobi').glob('*.mobi')), ['测试漫画_CH-001_to_CH-001.mobi'])

    def test_batch_mode_keeps_pdf_directory_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / 'input'
            out_dir = root / 'out'
            input_dir.mkdir()

            write_zip(
                input_dir / 'CH-001.zip',
                {
                    '001.jpg': build_jpeg_bytes(color=(255, 0, 0)),
                }
            )

            def fake_convert(pdf_path, mobi_output_dir, kindle_profile):
                mobi_path = Path(mobi_output_dir) / f'{Path(pdf_path).stem}.mobi'
                mobi_path.write_bytes(b'mobi')
                return str(mobi_path)

            with mock.patch.object(main, 'convert_pdf_to_mobi', side_effect=fake_convert):
                main.pack_comics_to_pdf(
                    str(input_dir),
                    batch_size=1,
                    pdf_prefix='测试漫画',
                    output_folder=str(out_dir),
                    convert_to_mobi=True,
                    comic_name='测试漫画'
                )

            comic_dir = out_dir / '测试漫画'
            self.assertTrue((comic_dir / 'pdf').is_dir())
            self.assertTrue(any((comic_dir / 'pdf').glob('*.pdf')))
            self.assertTrue((comic_dir / 'mobi').is_dir())


if __name__ == '__main__':
    unittest.main()
