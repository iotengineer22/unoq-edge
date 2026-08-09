import os
import re
import subprocess
import sys

# Paths - Dynamically generated to avoid hardcoded personal user directories
user_profile = os.environ.get("USERPROFILE", "C:\\Users\\default")
ADB_PATH = os.path.join(
    user_profile, 
    "AppData", "Local", "Arduino15", "packages", "arduino", "tools", "adb", "32.0.0", "adb.exe"
)
MAP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "zephyr", "zephyr.map")

RAW_FILE_ON_BOARD = "/tmp/captured.raw"
RAW_FILE_LOCAL = "./captured.raw"
PNG_FILE_LOCAL = "./captured.png"
BUFFER_SIZE = 18432  # 96 * 96 * 2 (Cropped)

LOG_FILE_ON_BOARD = "/tmp/inference_log.txt"
LOG_FILE_LOCAL = "./inference_log.txt"
LOG_BUFFER_SIZE = 2048

BOOT_CHECKPOINT_FILE_ON_BOARD = "/tmp/boot_checkpoint.txt"
BOOT_CHECKPOINT_FILE_LOCAL = "./boot_checkpoint.txt"
BOOT_CHECKPOINT_SIZE = 256

def get_symbol_address(symbol_name):
    if not os.path.exists(MAP_FILE):
        print(f"Error: Map file not found at {MAP_FILE}. Please build the project first.")
        sys.exit(1)
        
    print(f"Parsing zephyr.map to find '{symbol_name}' address...")
    # Read map file
    with open(MAP_FILE, "r") as f:
        content = f.read()
        
    # Match pattern: address followed by symbol
    # e.g., "0x20001178                image_buffer"
    match = re.search(r"(0x[0-9a-fA-F]+)\s+" + re.escape(symbol_name) + r"\b", content)
    if not match:
        print(f"Error: Could not find '{symbol_name}' in map file.")
        sys.exit(1)
        
    addr = match.group(1)
    print(f"Found '{symbol_name}' at RAM address: {addr}")
    return addr

def execute_cmd(cmd):
    # Print execution command for debugging (with quotes if spaces exist)
    print_cmd = []
    for c in cmd:
        if ' ' in c or '"' in c or '\\' in c:
            print_cmd.append(f'"{c}"')
        else:
            print_cmd.append(c)
    print(f"Executing: {' '.join(print_cmd)}")

    # Run with shell=False to prevent quote/escape issues on Windows
    result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    if result.returncode != 0:
        print(f"Command failed! Error:\n{result.stderr}\nStdout:\n{result.stdout}")
        return False
    return True

def install_pillow():
    try:
        from PIL import Image
    except ImportError:
        print("Pillow library not found. Installing via pip...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])

def clamp(val):
    return max(0, min(255, int(val)))

def convert_yuyv_to_png(raw_data, width, height):
    from PIL import Image
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    
    # YUYV (4:2:2): 4 bytes represent 2 pixels (Y0, U0, Y1, V0)
    for y in range(height):
        for x in range(0, width, 2):
            idx = (y * width + x) * 2
            if idx + 3 >= len(raw_data):
                break
            y0 = raw_data[idx]
            u0 = raw_data[idx + 1]
            y1 = raw_data[idx + 2]
            v0 = raw_data[idx + 3]
            
            # Pixel 1
            c = y0 - 16
            d = u0 - 128
            e = v0 - 128
            r0 = clamp((298 * c + 409 * e + 128) >> 8)
            g0 = clamp((298 * c - 100 * d - 208 * e + 128) >> 8)
            b0 = clamp((298 * c + 516 * d + 128) >> 8)
            pixels[x, y] = (r0, g0, b0)
            
            # Pixel 2
            c = y1 - 16
            r1 = clamp((298 * c + 409 * e + 128) >> 8)
            g1 = clamp((298 * c - 100 * d - 208 * e + 128) >> 8)
            b1 = clamp((298 * c + 516 * d + 128) >> 8)
            pixels[x + 1, y] = (r1, g1, b1)
    return img

def convert_uyvy_to_png(raw_data, width, height):
    from PIL import Image
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    
    # UYVY: 4 bytes represent 2 pixels (U0, Y0, V0, Y1)
    for y in range(height):
        for x in range(0, width, 2):
            idx = (y * width + x) * 2
            if idx + 3 >= len(raw_data):
                break
            u0 = raw_data[idx]
            y0 = raw_data[idx + 1]
            v0 = raw_data[idx + 2]
            y1 = raw_data[idx + 3]
            
            # Pixel 1
            c = y0 - 16
            d = u0 - 128
            e = v0 - 128
            r0 = clamp((298 * c + 409 * e + 128) >> 8)
            g0 = clamp((298 * c - 100 * d - 208 * e + 128) >> 8)
            b0 = clamp((298 * c + 516 * d + 128) >> 8)
            pixels[x, y] = (r0, g0, b0)
            
            # Pixel 2
            c = y1 - 16
            r1 = clamp((298 * c + 409 * e + 128) >> 8)
            g1 = clamp((298 * c - 100 * d - 208 * e + 128) >> 8)
            b1 = clamp((298 * c + 516 * d + 128) >> 8)
            pixels[x + 1, y] = (r1, g1, b1)
    return img

def convert_rgb565_shifted(raw_data, width, height, endian="be", shift=1):
    from PIL import Image
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            idx = (y * width + x) * 2 + shift
            if idx + 1 >= len(raw_data):
                break
            b1 = raw_data[idx]
            b2 = raw_data[idx + 1]
            if endian == "be":
                val = (b1 << 8) | b2
            else:
                val = (b2 << 8) | b1
            r = ((val >> 11) & 0x1F) << 3
            g = ((val >> 5) & 0x3F) << 2
            b = (val & 0x1F) << 3
            pixels[x, y] = (r, g, b)
    return img

def convert_rgb565_to_png(raw_path, png_path):
    print("Converting RAW data to multiple format options for debugging...")
    from PIL import Image
    
    with open(raw_path, "rb") as f:
        raw_data = f.read()
        
    if len(raw_data) < BUFFER_SIZE:
        print(f"Error: Raw file size ({len(raw_data)}) is smaller than expected size ({BUFFER_SIZE}).")
        return
        
    width = 96
    height = 96
    
    # 1. Little Endian (LE) RGB565
    img_le = Image.new("RGB", (width, height))
    pixels_le = img_le.load()
    
    # 2. Big Endian (BE) RGB565
    img_be = Image.new("RGB", (width, height))
    pixels_be = img_be.load()
    
    for y in range(height):
        for x in range(width):
            idx = (y * width + x) * 2
            b1 = raw_data[idx]
            b2 = raw_data[idx + 1]
            
            # LE
            val_le = (b2 << 8) | b1
            r_le = ((val_le >> 11) & 0x1F) << 3
            g_le = ((val_le >> 5) & 0x3F) << 2
            b_le = (val_le & 0x1F) << 3
            pixels_le[x, y] = (r_le, g_le, b_le)
            
            # BE
            val_be = (b1 << 8) | b2
            r_be = ((val_be >> 11) & 0x1F) << 3
            g_be = ((val_be >> 5) & 0x3F) << 2
            b_be = (val_be & 0x1F) << 3
            pixels_be[x, y] = (r_be, g_be, b_be)
            
    # Save base options
    img_le.save(png_path.replace(".png", "_le.png"))
    img_be.save(png_path.replace(".png", "_be.png"))
    
    # 3. Shifted versions (1 byte shift) to check alignment offset
    img_be_shift1 = convert_rgb565_shifted(raw_data, width, height, "be", 1)
    img_be_shift1.save(png_path.replace(".png", "_be_shift1.png"))
    
    img_le_shift1 = convert_rgb565_shifted(raw_data, width, height, "le", 1)
    img_le_shift1.save(png_path.replace(".png", "_le_shift1.png"))
    
    # 4. YUYV & UYVY format checks
    img_yuyv = convert_yuyv_to_png(raw_data, width, height)
    img_yuyv.save(png_path.replace(".png", "_yuyv.png"))
    
    img_uyvy = convert_uyvy_to_png(raw_data, width, height)
    img_uyvy.save(png_path.replace(".png", "_uyvy.png"))
    
    # Default preview is now BE (most standard)
    img_be.save(png_path)
    
    print("Saved all debug output images to project folder:")
    print(" - captured_le.png, captured_be.png (Normal RGB565)")
    print(" - captured_le_shift1.png, captured_be_shift1.png (1-byte Shifted RGB565)")
    print(" - captured_yuyv.png, captured_uyvy.png (YUV 4:2:2 Formats)")

def parse_inference_log(log_path):
    bboxes = []
    if not os.path.exists(log_path):
        return bboxes
        
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        log_content = f.read()
        
    # Pattern to match FOMO bounding box:
    # "  Connector (0.777344) [ x: 8, y: 0, w: 88, h: 88 ]"
    pattern = r"\s+([\w\d_-]+)\s+\(([\d.]+)\)\s+\[\s*x:\s*(\d+),\s*y:\s*(\d+),\s*w:\s*(\d+),\s*h:\s*(\d+)\s*\]"
    matches = re.findall(pattern, log_content)
    
    for m in matches:
        label = m[0]
        score = float(m[1])
        x = int(m[2])
        y = int(m[3])
        w = int(m[4])
        h = int(m[5])
        bboxes.append({
            "label": label,
            "score": score,
            "box": (x, y, w, h)
        })
    return bboxes

def draw_bounding_boxes(image_path, output_path, bboxes):
    from PIL import Image, ImageDraw
    
    if not os.path.exists(image_path):
        print(f"Base image not found at {image_path}")
        return
        
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    
    for bbox in bboxes:
        label = bbox["label"]
        score = bbox["score"]
        x, y, w, h = bbox["box"]
        
        # FOMO outputs (x, y) as the center (centroid) of the detected object.
        # Offset by half of width/height to center the bounding box around it.
        x0 = max(0, int(x - w / 2))
        y0 = max(0, int(y - h / 2))
        x1 = min(95, int(x + w / 2))
        y1 = min(95, int(y + h / 2))
        
        # Draw green bounding box rectangle
        draw.rectangle([x0, y0, x1, y1], outline=(0, 255, 0), width=1)
        
        # Draw label text
        text_str = f"{label}:{int(score*100)}%"
        # Position label inside or above the box
        text_y = y0 - 9 if y0 >= 9 else y0 + 2
        draw.text((x0 + 2, text_y), text_str, fill=(0, 255, 0))
        
    img.save(output_path)
    print(f"Saved image with bounding boxes to {output_path}")

def main():
    install_pillow()
    addr = get_symbol_address("image_buffer")
    log_addr = get_symbol_address("inference_log_buffer")
    checkpoint_addr = get_symbol_address("boot_checkpoint")
    
    # 1. Dump image, log & boot checkpoint from STM32 RAM to Board Linux /tmp
    openocd_cmd = (
        f"init; halt; "
        f"dump_image {RAW_FILE_ON_BOARD} {addr} {BUFFER_SIZE}; "
        f"dump_image {LOG_FILE_ON_BOARD} {log_addr} {LOG_BUFFER_SIZE}; "
        f"dump_image {BOOT_CHECKPOINT_FILE_ON_BOARD} {checkpoint_addr} {BOOT_CHECKPOINT_SIZE}; "
        f"resume; shutdown"
    )
    dump_cmd = [
        ADB_PATH, "shell",
        f"/opt/openocd/bin/openocd -d2 -s /opt/openocd -f openocd_gpiod.cfg -c \"{openocd_cmd}\""
    ]
    if not execute_cmd(dump_cmd):
        print("Failed to dump data from STM32 RAM.")
        sys.exit(1)
        
    # 2. Pull files from Board Linux to Host PC
    pull_cmd = [ADB_PATH, "pull", RAW_FILE_ON_BOARD, RAW_FILE_LOCAL]
    execute_cmd(pull_cmd)
    
    pull_log_cmd = [ADB_PATH, "pull", LOG_FILE_ON_BOARD, LOG_FILE_LOCAL]
    execute_cmd(pull_log_cmd)

    pull_cp_cmd = [ADB_PATH, "pull", BOOT_CHECKPOINT_FILE_ON_BOARD, BOOT_CHECKPOINT_FILE_LOCAL]
    execute_cmd(pull_cp_cmd)
        
    # 3. Convert RAW to PNG
    if os.path.exists(RAW_FILE_LOCAL):
        convert_rgb565_to_png(RAW_FILE_LOCAL, PNG_FILE_LOCAL)
        # Clean up board side temporary file
        execute_cmd([ADB_PATH, "shell", f"rm {RAW_FILE_ON_BOARD}"])
    else:
        print("Local RAW file not found.")
        
    # 4. Print and clean up Boot Checkpoint
    if os.path.exists(BOOT_CHECKPOINT_FILE_LOCAL):
        print("\n=== Firmware Boot Checkpoint ===")
        with open(BOOT_CHECKPOINT_FILE_LOCAL, "rb") as f:
            cp_bytes = f.read()
            null_idx = cp_bytes.find(b'\x00')
            if null_idx != -1:
                cp_bytes = cp_bytes[:null_idx]
            try:
                decoded_cp = cp_bytes.decode('utf-8')
                print(decoded_cp)
                with open(BOOT_CHECKPOINT_FILE_LOCAL, "w", encoding="utf-8") as f_out:
                    f_out.write(decoded_cp)
            except Exception as e:
                print(cp_bytes)
        print("=================================\n")
        execute_cmd([ADB_PATH, "shell", f"rm {BOOT_CHECKPOINT_FILE_ON_BOARD}"])

    # 5. Print and clean up Log, Parse BBoxes
    bboxes = []
    if os.path.exists(LOG_FILE_LOCAL):
        print("\n=== Edge Impulse Inference Result ===")
        with open(LOG_FILE_LOCAL, "rb") as f:
            log_bytes = f.read()
            null_idx = log_bytes.find(b'\x00')
            if null_idx != -1:
                log_bytes = log_bytes[:null_idx]
            try:
                decoded_log = log_bytes.decode('utf-8')
                print(decoded_log)
                with open(LOG_FILE_LOCAL, "w", encoding="utf-8") as f_out:
                    f_out.write(decoded_log)
            except Exception as e:
                print(f"Error decoding log: {e}")
                print(log_bytes)
        print("=====================================\n")
        
        # Parse bboxes from the temporary log file
        bboxes = parse_inference_log(LOG_FILE_LOCAL)
        execute_cmd([ADB_PATH, "shell", f"rm {LOG_FILE_ON_BOARD}"])
        
    # 6. Draw Bounding Boxes on the image
    if bboxes:
        # Use Big Endian normal png (captured_be.png) or default (captured.png)
        draw_bounding_boxes("./captured_be.png", "./captured_with_bbox.png", bboxes)
        
        # Copy to artifacts folder if it exists
        artifacts_dir = "C:\\Users\\ioten\\.gemini\\antigravity-cli\\brain\\15429326-517d-4d25-941c-6328551e1917"
        if os.path.exists(artifacts_dir) and os.path.exists("./captured_with_bbox.png"):
            import shutil
            shutil.copy("./captured_with_bbox.png", os.path.join(artifacts_dir, "captured_with_bbox.png"))
            print(f"Copied captured_with_bbox.png to artifacts folder.")

if __name__ == "__main__":
    main()
