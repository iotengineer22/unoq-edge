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
BUFFER_SIZE = 153600  # 320 * 240 * 2 (QVGA)

def get_buffer_address():
    if not os.path.exists(MAP_FILE):
        print(f"Error: Map file not found at {MAP_FILE}. Please build the project first.")
        sys.exit(1)
        
    print("Parsing zephyr.map to find 'image_buffer' address...")
    # Read map file
    with open(MAP_FILE, "r") as f:
        content = f.read()
        
    # Match pattern: address followed by image_buffer
    # e.g., "0x20001178                image_buffer"
    match = re.search(r"(0x[0-9a-fA-F]+)\s+image_buffer\b", content)
    if not match:
        print("Error: Could not find 'image_buffer' in map file.")
        sys.exit(1)
        
    addr = match.group(1)
    print(f"Found 'image_buffer' at RAM address: {addr}")
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
        
    width = 320
    height = 240
    
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

def main():
    install_pillow()
    addr = get_buffer_address()
    
    # 1. Dump image from STM32 RAM to Board Linux /tmp
    openocd_cmd = (
        f"init; halt; dump_image {RAW_FILE_ON_BOARD} {addr} {BUFFER_SIZE}; resume; shutdown"
    )
    dump_cmd = [
        ADB_PATH, "shell",
        f"/opt/openocd/bin/openocd -d2 -s /opt/openocd -f openocd_gpiod.cfg -c \"{openocd_cmd}\""
    ]
    if not execute_cmd(dump_cmd):
        print("Failed to dump image from STM32 RAM.")
        sys.exit(1)
        
    # 2. Pull raw image file from Board Linux to Host PC
    pull_cmd = [ADB_PATH, "pull", RAW_FILE_ON_BOARD, RAW_FILE_LOCAL]
    if not execute_cmd(pull_cmd):
        print("Failed to pull raw image file from board.")
        sys.exit(1)
        
    # 3. Convert RAW to PNG
    if os.path.exists(RAW_FILE_LOCAL):
        convert_rgb565_to_png(RAW_FILE_LOCAL, PNG_FILE_LOCAL)
        # Clean up board side temporary file
        execute_cmd([ADB_PATH, "shell", f"rm {RAW_FILE_ON_BOARD}"])
    else:
        print("Local RAW file not found.")

if __name__ == "__main__":
    main()
