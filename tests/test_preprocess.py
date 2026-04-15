import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


def build_image_bytes(fmt: str, size=(900, 1400), mode='RGB', color=None) -> bytes:
    if color is None:
        color = (128, 160, 192, 255) if 'A' in mode else (128, 160, 192)

    image = Image.new(mode, size, color)
    buffer = io.BytesIO()
    save_kwargs = {'format': fmt}
    if fmt.upper() == 'JPEG':
        image = image.convert('RGB')
        save_kwargs.update({'quality': 95})
    image.save(buffer, **save_kwargs)
    return buffer.getvalue()


class PreprocessTests(unittest.TestCase):
    def test_preprocess_image_reuses_rgb_jpeg_without_resize(self):
        image_bytes = build_image_bytes('JPEG', size=(1000, 1500), mode='RGB')

        result = main.preprocess_image((image_bytes, main.page_width, main.page_height, 'page-01.jpg'))

        self.assertIsNone(result['error'])
        self.assertEqual(result['data'], image_bytes)
        self.assertEqual(result['name'], 'page-01.jpg')
        expected_width, expected_height = main.calculate_page_dimensions(
            1000, 1500, main.page_width, main.page_height
        )
        self.assertEqual(result['width'], expected_width)
        self.assertEqual(result['height'], expected_height)

    def test_preprocess_image_flattens_rgba_png_to_rgb_jpeg(self):
        image_bytes = build_image_bytes('PNG', size=(900, 1400), mode='RGBA')

        result = main.preprocess_image((image_bytes, main.page_width, main.page_height, 'page-02.png'))

        self.assertIsNone(result['error'])
        self.assertNotEqual(result['data'], image_bytes)

        output_image = Image.open(io.BytesIO(result['data']))
        self.assertEqual(output_image.format, 'JPEG')
        self.assertEqual(output_image.mode, 'RGB')

    def test_get_preprocess_worker_count_honors_env_and_image_count(self):
        with mock.patch.dict(os.environ, {'COMICPACKER_PREPROCESS_WORKERS': '99'}, clear=False):
            self.assertEqual(main.get_preprocess_worker_count(3), 3)

        with mock.patch.dict(os.environ, {'COMICPACKER_PREPROCESS_WORKERS': '1'}, clear=False):
            self.assertEqual(main.get_preprocess_worker_count(10), 1)

    def test_get_preprocess_chunk_size_honors_env_and_image_count(self):
        with mock.patch.dict(os.environ, {'COMICPACKER_PREPROCESS_CHUNK_SIZE': '99'}, clear=False):
            self.assertEqual(main.get_preprocess_chunk_size(20), 20)

        with mock.patch.dict(os.environ, {'COMICPACKER_PREPROCESS_CHUNK_SIZE': '8'}, clear=False):
            self.assertEqual(main.get_preprocess_chunk_size(20), 8)

    def test_preprocess_images_preserves_input_order_in_parallel_mode(self):
        images = [
            (f'page-{index:02d}.jpg', build_image_bytes('JPEG', size=(2200 + index, 3200 + index)))
            for index in range(10)
        ]

        with mock.patch.dict(os.environ, {'COMICPACKER_PREPROCESS_WORKERS': '2'}, clear=False):
            result = main.preprocess_images(images, main.page_width, main.page_height, show_progress=False)

        self.assertEqual([item['name'] for item in result], [name for name, _ in images])


if __name__ == '__main__':
    unittest.main()
