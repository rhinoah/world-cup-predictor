#!/usr/bin/env python3
"""
make_icon.py
============
Genera prode.ico y prode.png: una copa de campeon (trofeo) dorada sobre un fondo
azul noche redondeado. Se usa como icono del acceso directo de la app.
Se dibuja en alta resolucion y se reduce, para bordes suaves.
"""
from PIL import Image, ImageDraw

R = 1024
def s(v): return int(v / 256 * R)
def pts(seq): return [(s(x), s(y)) for x, y in seq]
def box(b): return [s(v) for v in b]

img = Image.new("RGBA", (R, R), (0, 0, 0, 0))

# fondo: degrade vertical enmascarado en un cuadrado redondeado
grad = Image.new("RGB", (1, R))
top, bot = (0x24, 0x32, 0x57), (0x0e, 0x14, 0x26)
for y in range(R):
    t = y / R
    grad.putpixel((0, y), tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)))
grad = grad.resize((R, R))
mask = Image.new("L", (R, R), 0)
ImageDraw.Draw(mask).rounded_rectangle(box((8, 8, 248, 248)), radius=s(50), fill=255)
img.paste(grad, (0, 0), mask)

d = ImageDraw.Draw(img)
GOLD, GOLD_D, GOLD_L = (244, 198, 80), (201, 152, 44), (255, 232, 150)

# asas (detras del cuenco)
d.arc(box((42, 72, 88, 140)), 60, 300, fill=GOLD, width=s(13))
d.arc(box((168, 72, 214, 140)), 240, 120, fill=GOLD, width=s(13))

# cuenco
d.polygon(pts([(74, 78), (182, 78), (171, 116), (146, 150), (128, 163), (110, 150), (85, 116)]), fill=GOLD)
d.polygon(pts([(82, 86), (110, 86), (104, 140), (92, 116)]), fill=GOLD_L)   # highlight

# nudo + tallo + base
d.ellipse(box((108, 157, 148, 173)), fill=GOLD_D)
d.polygon(pts([(120, 171), (136, 171), (139, 193), (117, 193)]), fill=GOLD)
d.ellipse(box((102, 188, 154, 201)), fill=GOLD)
d.polygon(pts([(110, 197), (146, 197), (163, 219), (93, 219)]), fill=GOLD)
d.rounded_rectangle(box((85, 216, 171, 233)), radius=s(7), fill=GOLD_D)

out = img.resize((256, 256), Image.LANCZOS)
out.save("prode.png")
out.save("prode.ico", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("generado: prode.png + prode.ico")
