import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'computer-control-server'))
import screenshot


class ScreenshotTests(unittest.TestCase):
    def test_region_is_xy_width_height_not_pillow_bbox(self):
        with patch.object(screenshot.ImageGrab, 'grab', return_value=Image.new('RGB', (100, 60))) as grab:
            path, w, h = screenshot.capture([20, 30, 100, 60])
        self.addCleanup(lambda: Path(path).unlink(missing_ok=True))
        self.assertEqual((100, 60), (w, h))
        self.assertEqual((20, 30, 120, 90), grab.call_args.kwargs['bbox'])

    def test_capture_metadata_supports_crop_and_resized_coordinates(self):
        temp_root = Path(__file__).parent / '.tmp'
        temp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as out:
            with patch.object(screenshot.ImageGrab, 'grab', return_value=Image.new('RGB', (800, 600))):
                result = screenshot.capture_details([120, 50, 800, 600], output_dir=out)
            point = screenshot.map_coordinates(result, 200, 150, 400, 300)
            self.assertEqual({'x': 520, 'y': 350, 'coordinate_space': 'physical_pixels'}, point)

    def test_outside_image_coordinates_are_rejected(self):
        meta = {'width': 100, 'height': 100, 'origin_x': 0, 'origin_y': 0}
        with self.assertRaises(ValueError):
            screenshot.map_coordinates(meta, 100, 50)

    def test_negative_or_zero_region_dimensions_are_rejected(self):
        with self.assertRaises(ValueError):
            screenshot.capture([10, 20, -5, 10])


if __name__ == '__main__':
    unittest.main()
