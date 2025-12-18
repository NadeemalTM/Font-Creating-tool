import streamlit as st
import os
import math
import tempfile
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent, GlyphCoordinates
from fontTools.ttLib.tables import ttProgram
from PIL import Image, ImageDraw, ImageFont
import skeleton_utils

# --- Core Logic (Adapted from create_skeleton_font.py) ---

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
    gmap = {}
    for code, name in cmap.items():
        if name not in gmap:
            gmap[name] = chr(code)
    return gmap

def process_font_file(input_path, output_path, dot_radius, spacing, render_size, progress_bar=None):
    font = TTFont(input_path)
    glyph_order = font.getGlyphOrder()
    dot_name = create_dot_glyph(font, dot_radius=dot_radius)
    
    gmap = get_unicode_map(font)
    
    try:
        pil_font = ImageFont.truetype(input_path, render_size)
    except Exception as e:
        return f"Error loading font with Pillow: {e}"

    upm = font['head'].unitsPerEm
    ascent, descent = pil_font.getmetrics()
    scale_factor = upm / render_size
    
    count = 0
    glyf_table = font['glyf']
    total_glyphs = len(glyph_order)
    
    for idx, name in enumerate(glyph_order):
        if progress_bar:
            progress_bar.progress(idx / total_glyphs)
            
        if name == dot_name or name == '.notdef':
            continue
            
        if name not in gmap:
            continue
            
        char = gmap[name]
        
        # Render glyph
        img_w, img_h = render_size * 2, render_size * 2 # Margin
        img = Image.new('L', (img_w, img_h), 0)
        draw = ImageDraw.Draw(img)
        
        baseline_y = ascent + 50
        draw_x = 50
        draw.text((draw_x, baseline_y - ascent), char, font=pil_font, fill=255)
        
        bbox = img.getbbox()
        if not bbox:
            continue
            
        crop_img = img.crop(bbox)
        cw, ch = crop_img.size
        
        c_data = list(crop_img.getdata())
        c_pixels = []
        for y in range(ch):
            row = []
            for x in range(cw):
                val = c_data[y*cw + x]
                row.append(1 if val > 128 else 0)
            c_pixels.append(row)
            
        skeleton = skeleton_utils.skeletonize(c_pixels, cw, ch)
        paths = skeleton_utils.trace_skeleton(skeleton, cw, ch)
        
        bx, by = bbox[0], bbox[1]
        
        def transform_pt(px, py):
            gx = px + bx
            gy = py + by
            rel_x = gx - draw_x
            rel_y = gy - baseline_y
            fx = rel_x * scale_factor
            fy = -rel_y * scale_factor
            return (fx, fy)
            
        dots = []
        placed_dots_px = []
        pixel_spacing = spacing / scale_factor
        min_dist_sq = (pixel_spacing * 0.6) ** 2 
        
        def add_dot_checked(px, py):
            for ex, ey in placed_dots_px:
                if (px-ex)**2 + (py-ey)**2 < min_dist_sq:
                    return False
            
            fx, fy = transform_pt(px, py)
            dots.append((dot_name, (1, 0, 0, 1, int(fx), int(fy))))
            placed_dots_px.append((px, py))
            return True
            
        for path in paths:
            if not path: continue
            
            curr_pt = path[0]
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

    font.save(output_path)
    return count

# --- Streamlit UI ---

st.set_page_config(page_title="Dotted Font Generator", layout="wide")

st.title("Dotted Font Generator")
st.markdown("Upload a TTF font file to convert it into a single-line dotted font for handwriting practice.")

uploaded_file = st.file_uploader("Choose a TTF file", type="ttf")

if uploaded_file is not None:
    st.sidebar.header("Settings")
    
    dot_radius = st.sidebar.slider("Dot Radius", min_value=5, max_value=50, value=20, help="Radius of the dots in font units.")
    spacing = st.sidebar.slider("Dot Spacing", min_value=20, max_value=150, value=50, help="Distance between dots in font units.")
    render_size = st.sidebar.slider("Render Resolution", min_value=50, max_value=300, value=150, help="Higher resolution means smoother curves but slower processing.")
    
    if st.button("Generate Dotted Font"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ttf") as tmp_input:
            tmp_input.write(uploaded_file.getvalue())
            input_path = tmp_input.name
            
        output_path = input_path.replace(".ttf", "-Dotted.ttf")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text("Processing glyphs...")
        
        try:
            count = process_font_file(input_path, output_path, dot_radius, spacing, render_size, progress_bar)
            
            if isinstance(count, str): # Error message
                st.error(count)
            else:
                st.success(f"Successfully processed {count} glyphs!")
                
                with open(output_path, "rb") as f:
                    st.download_button(
                        label="Download Dotted Font",
                        data=f,
                        file_name=f"{uploaded_file.name.replace('.ttf', '')}-Dotted.ttf",
                        mime="font/ttf"
                    )
                    
        except Exception as e:
            st.error(f"An error occurred: {e}")
            
        finally:
            # Cleanup
            if os.path.exists(input_path):
                os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
