"""Small generated files for the demo data: PDFs and avatars.

Pure Python + Pillow (no Django), so it can be exercised on its own.
"""
import io

from PIL import Image, ImageDraw, ImageFont


def _escape(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(title, lines=()):
    """Return the bytes of a valid one-page PDF showing ``title`` and ``lines`` (Latin-1 text)."""
    def latin(text):
        return _escape(text.encode("latin-1", "replace").decode("latin-1"))

    content = ["BT", "/F1 20 Tf", "72 760 Td", f"({latin(title)}) Tj", "/F1 12 Tf"]
    for line in lines:
        content += ["0 -22 Td", f"({latin(line)}) Tj"]
    content.append("ET")
    stream = "\n".join(content).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow: fixed-size bitmap font
        return ImageFont.load_default()


def make_avatar(name, colour, size=256):
    """PNG bytes: a coloured square with the person's initials."""
    image = Image.new("RGB", (size, size), colour)
    draw = ImageDraw.Draw(image)
    words = [w for w in name.replace(".", " ").split() if w and w[0].isalpha() and w.lower() not in ("dr", "prof", "mr", "ms")]
    initials = "".join(w[0] for w in words[:2]).upper() or "?"
    font = _font(size // 2)
    box = draw.textbbox((0, 0), initials, font=font)
    draw.text(((size - (box[2] - box[0])) / 2, (size - (box[3] - box[1])) / 2 - box[1]), initials,
              font=font, fill=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
