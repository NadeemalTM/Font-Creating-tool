from fontTools.ttLib import TTFont

font_path = "FM-Malithi-x.ttf"
try:
    font = TTFont(font_path)
    print(f"Number of glyphs: {len(font.getGlyphOrder())}")
    print(f"First 20 glyphs: {font.getGlyphOrder()[:20]}")
    
    # Check cmap
    cmap = font.getBestCmap()
    print(f"Number of mapped characters: {len(cmap)}")
    print(f"Sample mapping: {list(cmap.items())[:10]}")
    
    # Check a specific glyph to see if it has contours
    glyph_set = font.getGlyphSet()
    first_glyph_name = font.getGlyphOrder()[10] # Skip .notdef etc
    print(f"Checking glyph: {first_glyph_name}")
    glyph = glyph_set[first_glyph_name]
    print(f"Is composite: {glyph.isComposite()}")
    
    # If it's not composite, check contours
    if not glyph.isComposite():
        # We need to access the glyf table directly for contour count in raw glyph
        raw_glyph = font['glyf'][first_glyph_name]
        print(f"Number of contours: {raw_glyph.numberOfContours}")
        
except Exception as e:
    print(f"Error inspecting font: {e}")
