import streamlit as st
import os
import math
import tempfile
import base64
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent, GlyphCoordinates
from fontTools.ttLib.tables import ttProgram
from PIL import Image, ImageDraw, ImageFont
import skeleton_utils

# --- Core Logic ---

def create_dash_glyph(font, dash_length=40, dash_thickness=10):
    glyph_name = "dash_marker"
    if glyph_name in font['glyf']:
        return glyph_name
        
    glyph = Glyph()
    glyph.numberOfContours = 1
    
    # Rectangle centered at 0,0
    half_l = dash_length / 2
    half_t = dash_thickness / 2
    
    coords = [
        (int(-half_l), int(-half_t)),
        (int(half_l), int(-half_t)),
        (int(half_l), int(half_t)),
        (int(-half_l), int(half_t))
    ]
    
    glyph.endPtsOfContours = [3]
    glyph.coordinates = GlyphCoordinates(coords)
    glyph.flags = bytearray([1, 1, 1, 1])
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

def process_font_file(input_path, output_path, dash_length, dash_gap, dash_thickness, render_size, smoothing_iters, progress_bar=None):
    font = TTFont(input_path)
    glyph_order = font.getGlyphOrder()
    
    # Create the dash component
    dash_name = create_dash_glyph(font, dash_length=dash_length, dash_thickness=dash_thickness)
    
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
            
        if name == dash_name or name == '.notdef':
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
            
        dashes = []
        
        # Spacing logic
        # Stride = dash_length + gap
        pixel_dash_len = dash_length / scale_factor
        pixel_gap_len = dash_gap / scale_factor
        pixel_stride = pixel_dash_len + pixel_gap_len
        
        def add_dash(px, py, angle_rad):
            fx, fy = transform_pt(px, py)
            f_angle = -angle_rad # Flip angle for font coords
            c = math.cos(f_angle)
            s = math.sin(f_angle)
            transform = [[c, -s], [s, c]]
            dashes.append((dash_name, transform, int(fx), int(fy)))

        for path in paths:
            if not path: continue
            
            # Smooth the path further if requested
            if smoothing_iters > 0:
                path = skeleton_utils.smooth_path(path, iterations=smoothing_iters)
            
            # Walk path
            current_path_dist = 0
            next_dash_center = pixel_dash_len / 2 # Start with a dash
            
            for i in range(len(path) - 1):
                p1 = path[i]
                p2 = path[i+1]
                
                seg_len = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
                if seg_len == 0: continue
                
                while next_dash_center <= current_path_dist + seg_len:
                    d_into_seg = next_dash_center - current_path_dist
                    t = d_into_seg / seg_len
                    nx = p1[0] + (p2[0]-p1[0]) * t
                    ny = p1[1] + (p2[1]-p1[1]) * t
                    
                    # Angle from segment
                    dx = p2[0] - p1[0]
                    dy = p2[1] - p1[1]
                    angle = math.atan2(dy, dx)
                    
                    add_dash(nx, ny, angle)
                    next_dash_center += pixel_stride
                    
                current_path_dist += seg_len

        if not dashes:
            continue

        g = glyf_table[name]
        g.numberOfContours = -1
        g.components = []
        
        for dn, transform, x, y in dashes:
            c = GlyphComponent()
            c.glyphName = dn
            c.x = x
            c.y = y
            c.transform = transform
            c.flags = 0x200 | 0x800 
            g.components.append(c)
            
        count += 1

    font.save(output_path)
    return count

# --- Streamlit UI ---

st.set_page_config(page_title="Dashed Font Generator", layout="wide")

st.title("Dashed Font Generator")
st.markdown("Upload a TTF font file to convert it into a single-line dashed font.")

# Sidebar
st.sidebar.header("Settings")
dash_length = st.sidebar.slider("Dash Length (Font Units)", 10, 100, 40)
dash_gap = st.sidebar.slider("Dash Gap (Font Units)", 10, 100, 20)
dash_thickness = st.sidebar.slider("Dash Thickness", 2, 20, 6)
render_size = st.sidebar.slider("Render Resolution", 100, 400, 200, help="Higher = smoother curves but slower")
smoothing_iters = st.sidebar.slider("Smoothing Iterations", 0, 10, 5, help="Higher = smoother paths")

uploaded_file = st.file_uploader("Choose a TTF file", type="ttf")

if "generated_font_path" not in st.session_state:
    st.session_state.generated_font_path = None

if uploaded_file is not None:
    if st.button("Generate Dashed Font"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ttf") as tmp_input:
            tmp_input.write(uploaded_file.getvalue())
            input_path = tmp_input.name
            
        output_path = input_path.replace(".ttf", "-Dashed.ttf")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text("Processing glyphs...")
        
        try:
            count = process_font_file(
                input_path, 
                output_path, 
                dash_length, 
                dash_gap, 
                dash_thickness, 
                render_size, 
                smoothing_iters,
                progress_bar=progress_bar
            )
            
            if isinstance(count, str):
                st.error(count)
            else:
                st.success(f"Successfully processed {count} glyphs!")
                st.session_state.generated_font_path = output_path
                
        except Exception as e:
            st.error(f"An error occurred: {e}")
            if os.path.exists(input_path): os.unlink(input_path)

    # Preview Section
    if st.session_state.generated_font_path and os.path.exists(st.session_state.generated_font_path):
        st.markdown("---")
        st.header("Preview")
        
        preview_text = st.text_input("Type text to preview:", "අ ආ ඇ ඈ ඉ ඊ උ ඌ")
        
        # Load font as base64
        with open(st.session_state.generated_font_path, "rb") as f:
            font_data = f.read()
            b64_font = base64.b64encode(font_data).decode()
            
        # CSS to inject font
        font_face = f"""
        <style>
        @font-face {{
            font-family: 'DashedFont';
            src: url('data:font/ttf;base64,{b64_font}') format('truetype');
        }}
        .dashed-text {{
            font-family: 'DashedFont';
            font-size: 64px;
            line-height: 1.5;
        }}
        </style>
        """
        st.markdown(font_face, unsafe_allow_html=True)
        st.markdown(f'<p class="dashed-text">{preview_text}</p>', unsafe_allow_html=True)
        
        # Download Button
        with open(st.session_state.generated_font_path, "rb") as f:
            st.download_button(
                label="Download Dashed Font",
                data=f,
                file_name=f"DashedFont.ttf",
                mime="font/ttf"
            )
