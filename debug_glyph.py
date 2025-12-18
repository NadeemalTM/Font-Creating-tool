import sys
import os
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
import skeleton_utils

INPUT_FONT = "FM-Malithi-x.ttf"
RENDER_SIZE = 150

def debug_glyph():
    if not os.path.exists(INPUT_FONT):
        print(f"Error: {INPUT_FONT} not found.")
        return

    font = TTFont(INPUT_FONT)
    # Pick a glyph that looks complex, e.g., a Sinhala letter
    # Let's try to find a glyph that is likely to be a letter
    cmap = font['cmap'].getBestCmap()
    
    # Sinhala range is roughly 0D80–0DFF
    target_char = None
    target_name = None
    
    for code, name in cmap.items():
        if 0x0D80 <= code <= 0x0DFF:
            target_char = chr(code)
            target_name = name
            break
            
    if not target_char:
        # Fallback to 'A' or similar if no Sinhala char found
        target_char = 'A'
        target_name = 'A'

    print(f"Debugging glyph: {target_name} (Unicode: {ord(target_char)})")

    try:
        pil_font = ImageFont.truetype(INPUT_FONT, RENDER_SIZE)
    except Exception as e:
        print(f"Error loading font: {e}")
        return

    # Render
    margin = 50
    w, h = 300, 300 # Arbitrary large canvas
    img = Image.new('L', (w, h), 0)
    draw = ImageDraw.Draw(img)
    
    # Draw centered-ish
    draw.text((margin, margin), target_char, font=pil_font, fill=255)
    
    # Crop
    bbox = img.getbbox()
    if not bbox:
        print("Empty glyph")
        return
        
    crop_img = img.crop(bbox)
    crop_img.save("debug_original.png")
    print("Saved debug_original.png")
    
    # Convert to 0/1
    cw, ch = crop_img.size
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
    
    # Save skeleton image
    skel_img = Image.new('L', (cw, ch), 0)
    skel_data = []
    for y in range(ch):
        for x in range(cw):
            skel_data.append(255 if skeleton[y][x] == 1 else 0)
    skel_img.putdata(skel_data)
    skel_img.save("debug_skeleton.png")
    print("Saved debug_skeleton.png")
    
    # Trace
    paths = skeleton_utils.trace_skeleton(skeleton, cw, ch)
    
    # Draw trace
    trace_img = Image.new('RGB', (cw, ch), (0, 0, 0))
    draw_trace = ImageDraw.Draw(trace_img)
    
    # Draw original faint
    for y in range(ch):
        for x in range(cw):
            if c_pixels[y][x]:
                trace_img.putpixel((x, y), (50, 50, 50))
                
    import random
    for path in paths:
        color = (random.randint(100, 255), random.randint(100, 255), random.randint(100, 255))
        if len(path) > 1:
            draw_trace.line(path, fill=color, width=1)
        else:
            draw_trace.point(path[0], fill=color)
            
    trace_img.save("debug_trace.png")
    print("Saved debug_trace.png")

if __name__ == "__main__":
    debug_glyph()
