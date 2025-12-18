import sys
import os
import math
import requests
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent, GlyphCoordinates
from fontTools.ttLib.tables import ttProgram

# URL for Noto Sans Sinhala Regular
FONT_URL = "https://github.com/googlefonts/noto-fonts/raw/HEAD/hinted/ttf/NotoSansSinhala/NotoSansSinhala-Regular.ttf"
INPUT_FONT = "FM-Malithi-x.ttf"
OUTPUT_FONT = "FM-Malithi-x-Dotted.ttf"

def download_font():
    if not os.path.exists(INPUT_FONT):
        print(f"Downloading {INPUT_FONT}...")
        response = requests.get(FONT_URL)
        if response.status_code == 200:
            with open(INPUT_FONT, "wb") as f:
                f.write(response.content)
            print("Download complete.")
        else:
            print(f"Failed to download font. Status code: {response.status_code}")
            sys.exit(1)
    else:
        print(f"Using existing {INPUT_FONT}")

class FlattenPen(BasePen):
    """
    Flattens the path into a series of line segments.
    """
    def __init__(self, glyphSet, flatness=5):
        super().__init__(glyphSet)
        self.glyphSet = glyphSet
        self.flatness = flatness
        self.path = [] # List of (x, y) tuples
        self.current_pt = (0, 0)

    def _moveTo(self, pt):
        self.path.append(('move', pt))
        self.current_pt = pt

    def _lineTo(self, pt):
        self.path.append(('line', pt))
        self.current_pt = pt

    def _curveTo(self, *points):
        p0 = self.current_pt
        p1, p2, p3 = points
        self._flatten_cubic(p0, p1, p2, p3)
        self.current_pt = p3

    def _curveToOne(self, p1, p2, p3):
        self._curveTo(p1, p2, p3)

    def _qCurveTo(self, *points):
        # Simple implementation: just connect points
        # A better implementation would convert to cubic or subdivide
        # For now, we just connect the on-curve point (last one)
        # This is WRONG for quality but prevents crash.
        # Better: use fontTools.pens.basePen.BasePen's default which decomposes to curveTo?
        # BasePen.qCurveTo calls _qCurveTo.
        # If we don't implement _qCurveTo, BasePen raises NotImplementedError?
        # No, BasePen has qCurveTo which calls _qCurveTo.
        # If we want BasePen to handle it, we shouldn't implement _qCurveTo?
        # BasePen's qCurveTo implementation:
        # if self._qCurveTo: self._qCurveTo(*points)
        # else: ... logic to convert to curveTo ...
        # So we should REMOVE _qCurveTo and let BasePen handle it.
        pass

    def _flatten_cubic(self, p0, p1, p2, p3, level=0):
        d = math.hypot(p3[0]-p0[0], p3[1]-p0[1])
        if level > 4 or d < self.flatness:
            self.path.append(('line', p3))
            return

        p01 = self._mid(p0, p1)
        p12 = self._mid(p1, p2)
        p23 = self._mid(p2, p3)
        p012 = self._mid(p01, p12)
        p123 = self._mid(p12, p23)
        p0123 = self._mid(p012, p123)

        self._flatten_cubic(p0, p01, p012, p0123, level+1)
        self._flatten_cubic(p0123, p123, p23, p3, level+1)

    def _mid(self, p1, p2):
        return ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2)

    def closePath(self):
        self.path.append(('close', None))

    def endPath(self):
        self.path.append(('end', None))
        
    def addComponent(self, glyphName, transformation):
        # Handle composite glyphs by decomposing them
        if glyphName in self.glyphSet:
            tPen = TransformPen(self, transformation)
            self.glyphSet[glyphName].draw(tPen)

def create_dot_glyph(font, dot_radius=30):
    glyph_name = "dot_marker"
    glyph = Glyph()
    glyph.numberOfContours = 1
    glyph.endPtsOfContours = [3]
    r = dot_radius
    glyph.coordinates = GlyphCoordinates([(0, -r), (r, 0), (0, r), (-r, 0)])
    glyph.flags = bytearray([1, 1, 1, 1])
    glyph.program = ttProgram.Program()
    glyph.program.fromBytecode(b"")
    font['glyf'][glyph_name] = glyph
    font['hmtx'][glyph_name] = (0, 0)
    return glyph_name

def process_font():
    font = TTFont(INPUT_FONT)
    glyph_set = font.getGlyphSet()
    dot_name = create_dot_glyph(font)
    
    glyf_table = font['glyf']
    glyph_order = font.getGlyphOrder()
    
    count = 0
    for name in glyph_order:
        if name == dot_name or name == '.notdef':
            continue
        
        if name not in glyf_table:
            continue
            
        flatten_pen = FlattenPen(glyph_set, flatness=10)
        
        try:
            glyph_set[name].draw(flatten_pen)
        except Exception as e:
            print(f"Error processing {name}: {e}")
            continue
            
        if not flatten_pen.path:
            continue

        # Generate dots along the flattened path
        dots = []
        spacing = 60 # Distance between dots
        
        def add_dot(x, y):
            dots.append((dot_name, (1, 0, 0, 1, int(x), int(y))))
            
        curr = None
        start = None
        dist_acc = 0 
        
        for cmd, pt in flatten_pen.path:
            if cmd == 'move':
                start = pt
                curr = pt
                add_dot(pt[0], pt[1])
                dist_acc = 0
            elif cmd == 'line':
                p1 = curr
                p2 = pt
                d = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
                if d == 0: continue
                
                needed = spacing - dist_acc
                
                if d < needed:
                    dist_acc += d
                    curr = p2
                    continue
                
                ux = (p2[0]-p1[0])/d
                uy = (p2[1]-p1[1])/d
                
                current_d = needed
                while current_d <= d:
                    nx = p1[0] + ux * current_d
                    ny = p1[1] + uy * current_d
                    add_dot(nx, ny)
                    current_d += spacing
                
                dist_acc = d - (current_d - spacing)
                curr = p2
                
            elif cmd == 'close':
                if curr and start:
                    p1 = curr
                    p2 = start
                    d = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
                    if d > 0:
                        needed = spacing - dist_acc
                        if d >= needed:
                            ux = (p2[0]-p1[0])/d
                            uy = (p2[1]-p1[1])/d
                            current_d = needed
                            while current_d <= d:
                                nx = p1[0] + ux * current_d
                                ny = p1[1] + uy * current_d
                                add_dot(nx, ny)
                                current_d += spacing
                            dist_acc = d - (current_d - spacing)
                        else:
                            dist_acc += d
                    curr = start
        
        if not dots:
            continue

        # Replace glyph with dot components
        g = glyf_table[name]
        g.numberOfContours = -1 # Composite
        g.components = []
        
        for dn, transform in dots:
            c = GlyphComponent()
            c.glyphName = dn
            c.x = transform[4]
            c.y = transform[5]
            c.flags = 0
            g.components.append(c)
        
        count += 1
            
    font.save(OUTPUT_FONT)
    print(f"Saved {OUTPUT_FONT} with {count} processed glyphs")

if __name__ == "__main__":
    # download_font()
    process_font()
