"""Physical-pixel captures with explicit crop origins and monitor selection."""

import math
import os
import tempfile
import uuid
from pathlib import Path
from PIL import ImageGrab
from display import monitors


def _bbox(region, monitor):
    if region is not None:
        if (not isinstance(region, (list, tuple)) or len(region) != 4
                or any(type(v) is not int for v in region)):
            raise ValueError('region must be [x, y, width, height] in physical pixels')
        x, y, width, height = region
        if width <= 0 or height <= 0:
            raise ValueError('region width and height must be positive')
        return (x, y, x + width, y + height)
    screens = monitors()
    if type(monitor) is not int or not 0 <= monitor < len(screens):
        raise ValueError(f'monitor must be between 0 and {len(screens) - 1}')
    m = screens[monitor]
    return (m['x'], m['y'], m['x'] + m['width'], m['y'] + m['height'])


def capture_details(region=None, monitor=0, output_dir=None):
    bbox = _bbox(region, monitor)
    try:
        img = ImageGrab.grab(bbox=bbox, all_screens=True).convert('RGB')
        if output_dir is None:
            fd, path = tempfile.mkstemp(suffix='.png', prefix='screenshot_')
            os.close(fd)
        else:
            folder = Path(output_dir).resolve()
            folder.mkdir(parents=True, exist_ok=True)
            path = str(folder / f'viewshot_{uuid.uuid4().hex}.png')
        img.save(path, 'PNG')
    except Exception as error:
        raise RuntimeError(f'Screen capture failed: {error}') from error
    return {'path': path, 'width': img.width, 'height': img.height,
            'origin_x': bbox[0], 'origin_y': bbox[1],
            'coordinate_space': 'physical_pixels', 'monitor': monitor}


def capture(region=None, monitor=0):
    meta = capture_details(region, monitor)
    return meta['path'], meta['width'], meta['height']


def get_screen_size():
    screen = monitors()[0]
    return screen['width'], screen['height']


def map_coordinates(meta, x, y, image_width=None, image_height=None):
    width = meta['width'] if image_width is None else image_width
    height = meta['height'] if image_height is None else image_height
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in (x, y, width, height)):
        raise ValueError('Coordinates and image dimensions must be finite numbers')
    if width <= 0 or height <= 0 or not (0 <= x < width and 0 <= y < height):
        raise ValueError('Point must be inside the analyzed image')
    screen_x = meta.get('origin_x', 0) + min(meta['width'] - 1, int(x * meta['width'] / width + 0.5))
    screen_y = meta.get('origin_y', 0) + min(meta['height'] - 1, int(y * meta['height'] / height + 0.5))
    return {'x': screen_x, 'y': screen_y, 'coordinate_space': 'physical_pixels'}
