"""Validated local demo images, kept with the SQLite database."""
import base64
import io
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_FILE_BYTES = 5 * 1024 * 1024


def prepare_image(encoded, kind):
    if not isinstance(encoded, str) or len(encoded) > ((MAX_FILE_BYTES+2)//3)*4:
        raise ValueError('Selecciona una imagen de hasta 5 MB')
    try:
        raw = base64.b64decode(encoded, validate=True)
        if not raw or len(raw) > MAX_FILE_BYTES:
            raise ValueError('La imagen debe pesar entre 1 byte y 5 MB')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('JPEG', 'PNG', 'WEBP'):
                    raise ValueError('Formatos admitidos: JPG, PNG y WebP')
                if source.width > 8000 or source.height > 8000 or source.width*source.height > 16000000:
                    raise ValueError('La imagen supera 16 megapíxeles o 8000 píxeles por lado')
                if getattr(source, 'is_animated', False):
                    raise ValueError('Selecciona una imagen sin animación')
                source.load()
                im = ImageOps.exif_transpose(source).convert('RGBA')
                im.thumbnail((320,320) if kind=='avatar' else (800,800) if kind=='product' else (1280,1280))
                clean = Image.new('RGB', im.size, 'white')
                clean.paste(im, mask=im.getchannel('A'))
                out = io.BytesIO()
                clean.save(out, format='JPEG', quality=85, optimize=True)
                return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('No se pudo leer la imagen. Usa JPG, PNG o WebP válido') from exc


def image_url(c, kind, target_id):
    row = c.execute('SELECT id FROM media WHERE kind=? AND target_id=? ORDER BY created DESC,id DESC LIMIT 1',(kind,target_id)).fetchone()
    return '/api/media/'+row['id'] if row else None
