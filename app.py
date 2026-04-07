# Smart Image Processor — Web version for Render deployment
# Adapted from bild-bearbeitung.ipynb for headless server environments.
# Uses Gradio file uploads instead of tkinter folder dialogs.

import os
import tempfile
import zipfile
import numpy as np
from PIL import Image
import gradio as gr
import time
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import cv2

# Import rembg for background removal
from rembg import remove


def has_white_background(image_path, margin=40, threshold=0.7):
    """
    Check if an image has a white background by analyzing edge pixels
    """
    try:
        img = Image.open(image_path).convert("RGB")
        img_np = np.array(img)

        h, w = img_np.shape[:2]

        # Extract edge regions
        top_edge = img_np[:margin, :].reshape(-1, 3)
        bottom_edge = img_np[-margin:, :].reshape(-1, 3)
        left_edge = img_np[:, :margin].reshape(-1, 3)
        right_edge = img_np[:, -margin:].reshape(-1, 3)

        # Combine all edge pixels
        all_edges = np.vstack([top_edge, bottom_edge, left_edge, right_edge])

        # Calculate how close pixels are to white
        # White is (255, 255, 255)
        white_distances = np.sum(np.abs(all_edges - 255), axis=1)

        # Count pixels that are close to white (within a small distance)
        # Lower distance means whiter pixels
        near_white_count = np.sum(white_distances < 30)  # Increased tolerance for "near white"
        total_edge_pixels = len(all_edges)

        white_percentage = near_white_count / total_edge_pixels

        print(f"White percentage for {image_path}: {white_percentage:.2%}")

        return white_percentage > threshold
    except Exception as e:
        print(f"Error checking background for {image_path}: {e}")
        return False


def find_object_bbox_aggressive(image_path, has_white_bg):
    """Find the bounding box of the main object using multiple methods"""
    # Load image
    img = Image.open(image_path).convert("RGBA")
    img_np = np.array(img)
    img_cv = cv2.cvtColor(img_np[:, :, :3], cv2.COLOR_RGBA2BGR)

    # Method 1: Using rembg alpha channel
    try:
        removed_bg = remove(img_np)
        alpha = removed_bg[:, :, 3]

        # Find non-transparent pixels
        non_transparent = np.where(alpha > 50)  # Lower threshold for better detection

        if len(non_transparent[0]) > 0:
            y_min, y_max = non_transparent[0].min(), non_transparent[0].max()
            x_min, x_max = non_transparent[1].min(), non_transparent[1].max()

            # Add a margin
            margin = 5
            x_min = max(0, x_min - margin)
            y_min = max(0, y_min - margin)
            x_max = min(img_np.shape[1] - 1, x_max + margin)
            y_max = min(img_np.shape[0] - 1, y_max + margin)

            return (x_min, y_min, x_max, y_max)
    except Exception as e:
        print(f"Error with rembg: {e}")

    # Method 2: For dark backgrounds, use inverse detection
    if not has_white_bg:
        # For dark backgrounds, detect the main object differently
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

        # Use Otsu's thresholding
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            # Get the largest contour
            largest_contour = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest_contour)

            # Add margin
            margin = 10
            x_min = max(0, x - margin)
            y_min = max(0, y - margin)
            x_max = min(img_np.shape[1] - 1, x + w + margin)
            y_max = min(img_np.shape[0] - 1, y + h + margin)

            return (x_min, y_min, x_max, y_max)

    # Method 3: Edge detection for complex cases
    edges = cv2.Canny(img_cv, 100, 200)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        # Get the largest contour
        largest_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)

        # Add margin
        margin = 15
        x_min = max(0, x - margin)
        y_min = max(0, y - margin)
        x_max = min(img_np.shape[1] - 1, x + w + margin)
        y_max = min(img_np.shape[0] - 1, y + h + margin)

        return (x_min, y_min, x_max, y_max)

    # If all else fails, return full image bounds
    return (0, 0, img_np.shape[1] - 1, img_np.shape[0] - 1)


def center_crop_to_square(img, final_size):
    """
    Center crop image to a square of final_size x final_size.
    If image is smaller than final_size in any dimension, it will be scaled up first.
    """
    width, height = img.size

    # First, scale the image so that the smaller dimension equals final_size
    if width < height:
        # Width is smaller, scale based on width
        scale_factor = final_size / width
        new_width = final_size
        new_height = int(height * scale_factor)
    else:
        # Height is smaller or equal, scale based on height
        scale_factor = final_size / height
        new_height = final_size
        new_width = int(width * scale_factor)

    # Resize the image
    img_resized = img.resize((new_width, new_height), Image.LANCZOS)

    # Now center crop to final_size x final_size
    left = (new_width - final_size) // 2
    top = (new_height - final_size) // 2
    right = left + final_size
    bottom = top + final_size

    img_cropped = img_resized.crop((left, top, right, bottom))

    return img_cropped


def process_single_image(args):
    """Process a single image"""
    input_path, output_path, padding, final_size, has_white_bg = args

    try:
        # Load the original image
        img = Image.open(input_path).convert("RGBA")

        if has_white_bg:
            # WHITE BACKGROUND: Apply padding and object detection
            # Find the object bounding box with more aggressive detection
            bbox = find_object_bbox_aggressive(input_path, has_white_bg)
            x_min, y_min, x_max, y_max = bbox

            # Crop the object with margin
            cropped = img.crop((x_min, y_min, x_max, y_max))

            # Calculate dimensions for resizing with padding
            obj_width = x_max - x_min
            obj_height = y_max - y_min

            # Apply padding
            available_size = final_size - (2 * padding)
            scale_factor = available_size / max(obj_width, obj_height)

            new_width = int(obj_width * scale_factor)
            new_height = int(obj_height * scale_factor)

            # Resize the cropped object
            resized = cropped.resize((new_width, new_height), Image.LANCZOS)

            # Create final image with padding on white background
            output_img = Image.new("RGBA", (final_size, final_size), (255, 255, 255, 255))

            # Calculate position to center the object
            x_offset = (final_size - new_width) // 2
            y_offset = (final_size - new_height) // 2

            # Paste the resized object onto the white background
            output_img.paste(resized, (x_offset, y_offset), resized if resized.mode == "RGBA" else None)

            print(f"Processed with padding: {input_path}")
            print(f"Object bbox: {bbox}")
            print(f"Resized to: {new_width}x{new_height}")
            print(f"Final size: {final_size}x{final_size}")
        else:
            # NON-WHITE BACKGROUND: Center crop to square
            output_img = center_crop_to_square(img, final_size)

            print(f"Processed with center crop: {input_path}")
            print(f"Original size: {img.size}")
            print(f"Final size: {final_size}x{final_size}")

        # Save the result (convert to RGB if necessary)
        if output_img.mode == "RGBA":
            # Check if alpha channel is needed
            alpha = np.array(output_img)[:, :, 3]
            if np.all(alpha == 255):
                # No transparency needed, convert to RGB
                output_img = output_img.convert("RGB")
            else:
                # Keep RGBA and save as PNG
                output_path = output_path.replace('.jpg', '.png')
        else:
            output_img = output_img.convert("RGB")

        output_img.save(output_path, format="PNG" if output_path.endswith('.png') else "JPEG", quality=95)

        return True, output_path
    except Exception as e:
        print(f"Error processing {input_path}: {e}")
        return False, None


def process_images(files, padding, final_size, progress=gr.Progress()):
    """Process uploaded images and return a ZIP of results."""
    if not files:
        return "No images uploaded.", None

    # Create temp directories
    tmp_output = tempfile.mkdtemp(prefix="processed_")

    SUPPORTED_EXT = {".png", ".jpg", ".jpeg", ".webp"}
    image_files = [
        f for f in files
        if os.path.splitext(f.name if hasattr(f, 'name') else f)[-1].lower() in SUPPORTED_EXT
    ]

    total_images = len(image_files)
    if total_images == 0:
        return "No supported images found (PNG, JPG, JPEG, WEBP).", None

    start_time = time.time()
    progress(0, desc="Starting...")

    # Check background and prepare tasks
    tasks = []
    white_bg_count = 0
    for img_file in image_files:
        img_path = img_file.name if hasattr(img_file, 'name') else img_file
        has_white = has_white_background(img_path)
        if has_white:
            white_bg_count += 1

        out_name = os.path.splitext(os.path.basename(img_path))[0] + ".jpg"
        output_path = os.path.join(tmp_output, out_name)
        tasks.append((img_path, output_path, padding, final_size, has_white))

    # Process images (use fewer workers on Render to respect memory)
    max_workers = min(os.cpu_count() or 2, 4)
    output_files = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_single_image, tasks))

        for i, (success, out_path) in enumerate(results, 1):
            progress(i / total_images, desc=f"Processing {i}/{total_images}")
            if success and out_path:
                output_files.append(out_path)

    progress(1.0, desc="Processing complete!")
    total_time = timedelta(seconds=int(time.time() - start_time))

    # Create ZIP file with all processed images
    zip_path = os.path.join(tempfile.gettempdir(), "processed_images.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fp in output_files:
            zf.write(fp, os.path.basename(fp))

    summary = f"""Processing completed in {total_time}.
- Processed {len(output_files)}/{total_images} images
- {white_bg_count} images had white background (object detection + padding applied)
- {total_images - white_bg_count} images had non-white background (center-cropped to square)"""

    return summary, zip_path


def create_gradio_interface():
    with gr.Blocks(title="Smart Image Processor") as app:
        gr.Markdown("# Smart Object Cropping and Resizing Tool")
        gr.Markdown("""**Two processing modes (auto-detected per image):**
- **White background images:** Detects objects, applies padding, keeps white background
- **Non-white background images:** Center-crops to square (no background changes)

**Upload your images below, adjust settings, and download the processed results as a ZIP.**""")

        with gr.Row():
            with gr.Column():
                file_input = gr.File(
                    label="Upload Images (PNG, JPG, JPEG, WEBP)",
                    file_count="multiple",
                    file_types=["image"],
                )
                with gr.Row():
                    padding = gr.Slider(
                        minimum=0, maximum=500, value=80, step=10,
                        label="Padding (px) — applied only to white background images"
                    )
                    final_size = gr.Slider(
                        minimum=500, maximum=5000, value=1500, step=100,
                        label="Final Image Size (px)"
                    )
                process_btn = gr.Button("Process Images", variant="primary")

            with gr.Column():
                output_text = gr.Textbox(label="Processing Results", lines=8)
                output_file = gr.File(label="Download Processed Images (ZIP)")

        process_btn.click(
            fn=process_images,
            inputs=[file_input, padding, final_size],
            outputs=[output_text, output_file],
        )

    return app


if __name__ == "__main__":
    app = create_gradio_interface()
    app.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
    )
