import base64
import importlib.util
import io
from pathlib import Path
import unittest
from PIL import Image

spec=importlib.util.spec_from_file_location('lumigo_media',Path(__file__).resolve().parents[1]/'media.py')
media=importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)


class MediaValidation(unittest.TestCase):
    def test_reencodes_strips_metadata_and_applies_orientation(self):
        im=Image.new('RGB',(40,20),'red')
        exif=Image.Exif();exif[274]=6;exif[270]='private metadata'
        stream=io.BytesIO();im.save(stream,format='JPEG',exif=exif)
        result=media.prepare_image(base64.b64encode(stream.getvalue()).decode(),'avatar')
        cleaned=Image.open(io.BytesIO(result))
        self.assertEqual(cleaned.size,(20,40))
        self.assertEqual(dict(cleaned.getexif()),{})
        self.assertNotIn(b'private metadata',result)

    def test_rejects_non_images_and_oversized_input(self):
        for raw in (b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',b'not an image'):
            with self.assertRaises(ValueError):
                media.prepare_image(base64.b64encode(raw).decode(),'product')
        with self.assertRaises(ValueError):
            media.prepare_image('a'*(7*1024*1024),'product')
        stream=io.BytesIO();Image.new('RGB',(8001,1)).save(stream,format='PNG')
        with self.assertRaises(ValueError):
            media.prepare_image(base64.b64encode(stream.getvalue()).decode(),'product')

    def test_thumbnail_and_transparency(self):
        stream=io.BytesIO();Image.new('RGBA',(1200,600),(0,0,0,0)).save(stream,format='PNG')
        result=media.prepare_image(base64.b64encode(stream.getvalue()).decode(),'avatar')
        cleaned=Image.open(io.BytesIO(result))
        self.assertEqual(cleaned.size,(320,160))
        self.assertEqual(cleaned.getpixel((0,0)),(255,255,255))

if __name__=='__main__':
    unittest.main()
