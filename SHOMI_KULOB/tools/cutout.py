"""Non-destructive cutouts: official logo and dish photos from menu files.

Logo: only the *external* white background is removed (flood fill from the
image border, stopped by the logo's own outline); nothing inside the logo
is touched.  Dishes: a soft elliptical matte around the plate plus a white
key outside a protected core, with feathered edges where the menu cropped
the plate.  Food pixels themselves are never recoloured or reshaped; the
only processing is uniform scaling with a mild unsharp mask.
"""
from collections import deque

import numpy as np
from PIL import Image, ImageFilter


def logo_cutout(path, tol=28):
    """Return RGBA logo with the outer near-white background made transparent."""
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.int16)
    h, w, _ = a.shape
    white = (a.min(-1) > 255 - tol) & ((a.max(-1) - a.min(-1)) < 18)
    bg = np.zeros((h, w), bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if white[y, x] and not bg[y, x]:
                bg[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if white[y, x] and not bg[y, x]:
                bg[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and white[ny, nx] and not bg[ny, nx]:
                bg[ny, nx] = True
                q.append((ny, nx))
    alpha = Image.fromarray(np.where(bg, 0, 255).astype(np.uint8))
    # 1 px anti-aliased edge: slight blur of the matte, never shrinks the logo.
    alpha = alpha.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.0))
    out = im.convert("RGBA")
    out.putalpha(alpha)
    return out.crop(out.getbbox())


def dish_cutout(path, box, ellipse, width, feather=0.10, sharpen=True):
    """Cut one dish out of a menu image.

    box     -- (x0, y0, x1, y1) crop in source pixels
    ellipse -- (cx, cy, rx, ry) as fractions of the crop
    width   -- output width in pixels (uniform scale)
    """
    src = Image.open(path).convert("RGB").crop(tuple(box))
    sw, sh = src.size
    scale = width / sw
    img = src.resize((width, int(sh * scale)), Image.LANCZOS)
    if sharpen and scale > 1.2:
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=55, threshold=2))
    W, H = img.size
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy, rx, ry = ellipse
    d = np.sqrt(((xx / W - cx) / rx) ** 2 + ((yy / H - cy) / ry) ** 2)
    m = np.clip((1.0 - d) / feather, 0, 1)
    # Key out pure white menu paper, but only outside the protected core.
    a = np.asarray(img).astype(np.float32)
    whiteness = np.clip((a.min(-1) - 225) / 25, 0, 1) * (a.max(-1) - a.min(-1) < 25)
    m *= 1 - whiteness * (d > 0.75)
    # Feather any side where the matte touches the crop edge.
    edge = np.minimum.reduce([xx / W, (W - xx) / W, yy / H, (H - yy) / H])
    m *= np.clip(edge / 0.07, 0, 1)
    out = img.convert("RGBA")
    out.putalpha(Image.fromarray((m * 255).astype(np.uint8)))
    return out
