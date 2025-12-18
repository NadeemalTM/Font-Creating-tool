import sys
import os
import math
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent, GlyphCoordinates
from fontTools.ttLib.tables import ttProgram
from PIL import Image, ImageDraw, ImageFont
import skeleton_utils

INPUT_FONT = "FM-Malithi-x.ttf"
OUTPUT_FONT = "FM-Malithi-x-Skeleton-Dotted.ttf"
RENDER_SIZE = 150  # Height in pixels for skeletonization

def create_dot_glyph(font, dot_radius=20):
    glyph_name = "dot_marker"
    if glyph_name in font['glyf']:
        return glyph_name
        
    glyph = Glyph()
    glyph.numberOfContours = 1
    
    # Create a 12-sided polygon to approximate a circle
    num_points = 12
    coords = []
    for i in range(num_points):
        angle = 2 * math.pi * i / num_points
        x = int(dot_radius * math.cos(angle))
        y = int(dot_radius * math.sin(angle))
        coords.append((x, y))
        
    glyph.endPtsOfContours = [num_points - 1]
    glyph.coordinates = GlyphCoordinates(coords)
    glyph.flags = bytearray([1] * num_points)
    glyph.program = ttProgram.Program()
    glyph.program.fromBytecode(b"")
    font['glyf'][glyph_name] = glyph
    font['hmtx'][glyph_name] = (0, 0)
    return glyph_name

def get_unicode_map(font):
    cmap = font['cmap'].getBestCmap()
    # Reverse map: glyph name -> unicode
    # Note: a glyph might have multiple unicodes, we just pick one
    gmap = {}
    for code, name in cmap.items():
        if name not in gmap:
            gmap[name] = chr(code)
    return gmap

def process_font():
    if not os.path.exists(INPUT_FONT):
        print(f"Error: {INPUT_FONT} not found.")
        return

    font = TTFont(INPUT_FONT)
    glyph_order = font.getGlyphOrder()
    dot_name = create_dot_glyph(font, dot_radius=20)
    
    gmap = get_unicode_map(font)
    
    # Load Pillow font
    try:
        pil_font = ImageFont.truetype(INPUT_FONT, RENDER_SIZE)
    except Exception as e:
        print(f"Error loading font with Pillow: {e}")
        return

    # Get metrics to scale back
    # Pillow metrics are in pixels.
    # Font unitsPerEm is usually 1024 or 2048.
    # Scale factor = unitsPerEm / RENDER_SIZE ?
    # Not exactly. Pillow size is roughly the em-height in pixels.
    # We need to align the baseline.
    
    upm = font['head'].unitsPerEm
    ascent, descent = pil_font.getmetrics()
    # total height = ascent + descent
    # scale = upm / RENDER_SIZE (approx)
    
    # Better way:
    # Render a glyph, get its bbox in pixels.
    # Get glyph bbox in font units.
    # Calculate scale.
    # But skeletonization changes the shape (thins it).
    # We should rely on the font size.
    # If we request size=RENDER_SIZE, then 1 pixel = upm / RENDER_SIZE units?
    # Usually: size in pixels = size in points * dpi / 72.
    # ImageFont.truetype(..., size) specifies size in pixels (if index is not used? No, it's points usually, but Pillow treats it as pixels for bitmap fonts, for TTF it's size in points? No, it's size in pixels effectively).
    
    # Let's assume linear scaling.
    scale_factor = upm / RENDER_SIZE
    
    # We need to handle baseline offset.
    # In Pillow, (0,0) is top-left. Text is drawn at some (x, y).
    # If we draw at (0, ascent), the baseline is at y=ascent.
    # In TTF, baseline is y=0.
    # So pixel (x, y) corresponds to:
    # font_x = x * scale_factor
    # font_y = (ascent - y) * scale_factor
    
    count = 0
    glyf_table = font['glyf']
    
    for name in glyph_order:
        if name == dot_name or name == '.notdef':
            continue
            
        if name not in gmap:
            # Skip glyphs without unicode for now
            # print(f"Skipping {name} (no unicode)")
            continue
            
        char = gmap[name]
        
        # Render glyph
        # Create image large enough
        # Get mask
        try:
            mask = pil_font.getmask(char)
        except Exception as e:
            print(f"Failed to render {name}: {e}")
            continue
            
        # Mask size
        w, h = mask.size
        if w == 0 or h == 0:
            continue
            
        # Convert mask to 0/1 grid
        # mask is a flat bytes object
        pixels = []
        for y in range(h):
            row = []
            for x in range(w):
                # mask value 0-255. Threshold at 128?
                val = mask.getpixel((x, y)) if hasattr(mask, 'getpixel') else mask[y*w + x]
                row.append(1 if val > 128 else 0)
            pixels.append(row)
            
        # Skeletonize
        # print(f"Skeletonizing {name} ({w}x{h})...")
        skeleton = skeleton_utils.skeletonize(pixels, w, h)
        
        # Trace
        paths = skeleton_utils.trace_skeleton(skeleton, w, h)
        
        if not paths:
            continue
            
        # Convert paths to font units and add dots
        dots = []
        spacing = 50 # Font units
        
        # We need to adjust spacing based on scale?
        # If spacing is 60 in font units, we use it directly on scaled coordinates.
        
        # Get offset from mask?
        # mask doesn't have offset info directly if used like this.
        # We should use font.getbbox(char) to find where the glyph is drawn relative to (0,0).
        # bbox = pil_font.getbbox(char) -> (left, top, right, bottom)
        # This bbox is relative to the drawing position (0,0).
        # But getmask returns the tight bounding box of the glyph?
        # No, getmask returns an image.
        # If we use ImageDraw.text, we can control position.
        
        # Let's use ImageDraw to be sure about positioning.
        # Create a large image
        img_w, img_h = w + 100, h + 100 # Margin
        img = Image.new('L', (img_w, img_h), 0)
        draw = ImageDraw.Draw(img)
        
        # Draw text at a known position
        # We want baseline at some Y.
        baseline_y = ascent + 50 # 50 is margin
        draw_x = 50
        draw.text((draw_x, baseline_y - ascent), char, font=pil_font, fill=255)
        
        # Now read pixels from img
        # Crop to bbox to save processing?
        bbox = img.getbbox()
        if not bbox:
            continue
            
        crop_img = img.crop(bbox)
        cw, ch = crop_img.size
        
        # Convert to list
        c_data = list(crop_img.getdata())
        c_pixels = []
        for y in range(ch):
            row = []
            for x in range(cw):
                val = c_data[y*cw + x]
                row.append(1 if val > 128 else 0)
            c_pixels.append(row)
            
        # Skeletonize
        skeleton = skeleton_utils.skeletonize(c_pixels, cw, ch)
        paths = skeleton_utils.trace_skeleton(skeleton, cw, ch)
        
        # Transform points back to font units
        # Pixel (px, py) in crop_img
        # Global pixel (gx, gy) = (px + bbox[0], py + bbox[1])
        # Relative to baseline origin (draw_x, baseline_y):
        # rel_x = gx - draw_x
        # rel_y = gy - baseline_y
        # Font units:
        # fx = rel_x * scale_factor
        # fy = -rel_y * scale_factor (since y is down in pixels, up in font)
        
        bx, by = bbox[0], bbox[1]
        
        def transform_pt(px, py):
            gx = px + bx
            gy = py + by
            rel_x = gx - draw_x
            rel_y = gy - baseline_y
            fx = rel_x * scale_factor
            fy = -rel_y * scale_factor
            return (fx, fy)
            
        # Generate dots
        placed_dots_px = [] # Store (px, py) of placed dots to check distance
        pixel_spacing = spacing / scale_factor
        min_dist_sq = (pixel_spacing * 0.6) ** 2 
        
        def add_dot_checked(px, py):
            # Check distance against all placed dots
            for ex, ey in placed_dots_px:
                if (px-ex)**2 + (py-ey)**2 < min_dist_sq:
                    return False
            
            fx, fy = transform_pt(px, py)
            dots.append((dot_name, (1, 0, 0, 1, int(fx), int(fy))))
            placed_dots_px.append((px, py))
            return True
            
        for path in paths:
            if not path: continue
            
            # Path is list of (x, y)
            # Convert to font units first?
            # Or walk in pixels and convert dots?
            # Walking in pixels is easier for distance calculation if we scale spacing.
            # Pixel spacing = spacing / scale_factor
            
            # pixel_spacing is already defined above
            
            curr_idx = 0
            curr_pt = path[0]
            
            # Add first dot
            add_dot_checked(curr_pt[0], curr_pt[1])
            
            dist_acc = 0
            
            for i in range(len(path) - 1):
                p1 = path[i]
                p2 = path[i+1]
                
                d = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
                if d == 0: continue
                
                needed = pixel_spacing - dist_acc
                
                if d < needed:
                    dist_acc += d
                    continue
                    
                ux = (p2[0]-p1[0])/d
                uy = (p2[1]-p1[1])/d
                
                current_d = needed
                while current_d <= d:
                    nx = p1[0] + ux * current_d
                    ny = p1[1] + uy * current_d
                    
                    add_dot_checked(nx, ny)
                    
                    current_d += pixel_spacing
                    
                dist_acc = d - (current_d - pixel_spacing)

        if not dots:
            continue

        # Replace glyph
        g = glyf_table[name]
        g.numberOfContours = -1
        g.components = []
        
        for dn, transform in dots:
            c = GlyphComponent()
            c.glyphName = dn
            c.x = transform[4]
            c.y = transform[5]
            c.flags = 0
            g.components.append(c)
            
        count += 1
        if count % 10 == 0:
            print(f"Processed {count} glyphs...")

    font.save(OUTPUT_FONT)
    print(f"Saved {OUTPUT_FONT} with {count} processed glyphs")

if __name__ == "__main__":
    process_font()
