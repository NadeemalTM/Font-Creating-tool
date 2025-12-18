from PIL import Image
import statistics

def analyze():
    try:
        img = Image.open("debug_original.png")
        img = img.convert("L")
        w, h = img.size
        pixels = list(img.getdata())
        
        # Find bounding box of foreground (>128)
        fg_indices = [i for i, p in enumerate(pixels) if p > 128]
        if not fg_indices:
            print("Image is empty")
            return

        xs = [i % w for i in fg_indices]
        ys = [i // w for i in fg_indices]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        print(f"BBox: {min_x},{min_y} to {max_x},{max_y}")
        
        # Check center of bbox
        center_x = (min_x + max_x) // 2
        center_y = (min_y + max_y) // 2
        
        center_val = pixels[center_y * w + center_x]
        print(f"Center pixel ({center_x}, {center_y}) value: {center_val}")
        
        # Check a cross section
        row_y = center_y
        row_vals = [pixels[row_y * w + x] for x in range(min_x, max_x + 1)]
        # Print a simplified representation
        row_str = "".join(["#" if v > 128 else "." for v in row_vals])
        print(f"Cross section at Y={row_y}:")
        print(row_str)
        
        # Analyze skeleton
        skel = Image.open("debug_skeleton.png").convert("L")
        skel_pixels = list(skel.getdata())
        skel_fg = [p for p in skel_pixels if p > 128]
        print(f"Skeleton pixels: {len(skel_fg)}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze()
