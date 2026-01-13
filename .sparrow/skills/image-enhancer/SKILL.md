---
name: image-enhancer
description: Improves image and screenshot quality by enhancing resolution, sharpness, clarity, and overall visual quality. Use when improving customer-submitted screenshots, enhancing images for KB articles, or upscaling low-resolution attachments.
---

# Image Enhancer Skill

## Overview

Image quality improvement toolkit for enhancing screenshots, attachments, and visual content. Covers sharpening, noise reduction, contrast adjustment, and upscaling.

## When to Use

- Enhance customer-submitted screenshots for analysis
- Improve image quality for KB articles
- Upscale low-resolution attachments
- Clean up scanned documents
- Optimize images for display

## Basic Enhancement with Pillow

### Sharpening

```python
from PIL import Image, ImageEnhance, ImageFilter

def sharpen_image(image_path, output_path, factor=1.5):
    """Enhance image sharpness."""
    img = Image.open(image_path)

    # Apply sharpening filter
    sharpened = img.filter(ImageFilter.SHARPEN)

    # Additional enhancement
    enhancer = ImageEnhance.Sharpness(sharpened)
    result = enhancer.enhance(factor)

    result.save(output_path, quality=95)
    return output_path

# Usage
sharpen_image('blurry_screenshot.png', 'sharp_screenshot.png', factor=2.0)
```

### Contrast and Brightness

```python
from PIL import Image, ImageEnhance

def enhance_contrast_brightness(image_path, output_path, contrast=1.2, brightness=1.1):
    """Adjust contrast and brightness."""
    img = Image.open(image_path)

    # Enhance contrast
    contrast_enhancer = ImageEnhance.Contrast(img)
    img = contrast_enhancer.enhance(contrast)

    # Enhance brightness
    brightness_enhancer = ImageEnhance.Brightness(img)
    img = brightness_enhancer.enhance(brightness)

    img.save(output_path, quality=95)
    return output_path
```

### Color Enhancement

```python
from PIL import Image, ImageEnhance

def enhance_colors(image_path, output_path, saturation=1.2):
    """Enhance color saturation."""
    img = Image.open(image_path)

    enhancer = ImageEnhance.Color(img)
    result = enhancer.enhance(saturation)

    result.save(output_path, quality=95)
    return output_path
```

## Noise Reduction

```python
from PIL import Image, ImageFilter

def reduce_noise(image_path, output_path, iterations=1):
    """Apply noise reduction using median filter."""
    img = Image.open(image_path)

    # Apply median filter (good for removing noise while preserving edges)
    for _ in range(iterations):
        img = img.filter(ImageFilter.MedianFilter(size=3))

    img.save(output_path, quality=95)
    return output_path
```

## Upscaling

### Basic Upscale with Pillow

```python
from PIL import Image

def upscale_image(image_path, output_path, scale_factor=2):
    """Upscale image using high-quality resampling."""
    img = Image.open(image_path)

    new_width = int(img.width * scale_factor)
    new_height = int(img.height * scale_factor)

    # LANCZOS provides high-quality upscaling
    upscaled = img.resize((new_width, new_height), Image.LANCZOS)

    upscaled.save(output_path, quality=95)
    return output_path
```

### Advanced Upscaling with OpenCV

```python
import cv2
import numpy as np

def upscale_opencv(image_path, output_path, scale_factor=2):
    """Upscale using OpenCV's super resolution (if available)."""
    img = cv2.imread(image_path)

    # Calculate new dimensions
    width = int(img.shape[1] * scale_factor)
    height = int(img.shape[0] * scale_factor)

    # Use INTER_CUBIC for good quality upscaling
    upscaled = cv2.resize(img, (width, height), interpolation=cv2.INTER_CUBIC)

    cv2.imwrite(output_path, upscaled)
    return output_path
```

## Screenshot Enhancement Pipeline

```python
from PIL import Image, ImageEnhance, ImageFilter

def enhance_screenshot(image_path, output_path):
    """Complete screenshot enhancement pipeline."""
    img = Image.open(image_path)

    # Step 1: Slight noise reduction
    img = img.filter(ImageFilter.MedianFilter(size=3))

    # Step 2: Sharpen
    img = img.filter(ImageFilter.SHARPEN)
    sharpener = ImageEnhance.Sharpness(img)
    img = sharpener.enhance(1.3)

    # Step 3: Enhance contrast slightly
    contrast = ImageEnhance.Contrast(img)
    img = contrast.enhance(1.1)

    # Step 4: Ensure good brightness
    brightness = ImageEnhance.Brightness(img)
    img = brightness.enhance(1.05)

    img.save(output_path, quality=95)
    return output_path
```

## Text Screenshot Optimization

For screenshots containing text (most support scenarios):

```python
from PIL import Image, ImageFilter, ImageEnhance

def optimize_text_screenshot(image_path, output_path):
    """Optimize screenshot for text readability."""
    img = Image.open(image_path)

    # Convert to grayscale for text-heavy images (optional)
    # img = img.convert('L').convert('RGB')

    # Increase contrast for better text visibility
    contrast = ImageEnhance.Contrast(img)
    img = contrast.enhance(1.4)

    # Slight sharpening
    sharpener = ImageEnhance.Sharpness(img)
    img = sharpener.enhance(1.5)

    # Unsharp mask for edge enhancement
    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=100, threshold=2))

    img.save(output_path, quality=95)
    return output_path
```

## Batch Processing

```python
from pathlib import Path

def batch_enhance(input_dir, output_dir, enhancement_fn):
    """Apply enhancement to all images in directory."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}
    results = []

    for img_file in input_path.iterdir():
        if img_file.suffix.lower() in extensions:
            output_file = output_path / f"enhanced_{img_file.name}"
            try:
                enhancement_fn(str(img_file), str(output_file))
                results.append({'file': img_file.name, 'status': 'success'})
            except Exception as e:
                results.append({'file': img_file.name, 'status': 'failed', 'error': str(e)})

    return results

# Usage
results = batch_enhance('./screenshots', './enhanced', enhance_screenshot)
```

## Image Quality Assessment

```python
from PIL import Image
import numpy as np

def assess_image_quality(image_path):
    """Basic image quality assessment."""
    img = Image.open(image_path)
    img_array = np.array(img)

    metrics = {
        'dimensions': f"{img.width}x{img.height}",
        'mode': img.mode,
        'file_size_kb': Path(image_path).stat().st_size / 1024,
    }

    # Estimate sharpness (Laplacian variance)
    if len(img_array.shape) == 3:
        gray = np.mean(img_array, axis=2)
    else:
        gray = img_array

    laplacian = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]])
    from scipy.ndimage import convolve
    edges = convolve(gray.astype(float), laplacian)
    metrics['sharpness_score'] = np.var(edges)

    # Brightness
    metrics['avg_brightness'] = np.mean(gray)

    # Contrast (standard deviation)
    metrics['contrast_score'] = np.std(gray)

    return metrics
```

## Quick Reference

| Enhancement | Method | Factor Range |
|-------------|--------|--------------|
| Sharpness | `ImageEnhance.Sharpness()` | 1.0-2.0 |
| Contrast | `ImageEnhance.Contrast()` | 1.0-1.5 |
| Brightness | `ImageEnhance.Brightness()` | 0.8-1.2 |
| Saturation | `ImageEnhance.Color()` | 1.0-1.5 |
| Noise reduction | `ImageFilter.MedianFilter()` | size=3 |
| Upscale | `Image.resize()` | LANCZOS |

## Integration with Agent Sparrow

- **Ticket Screenshots**: Enhance customer-submitted images for analysis
- **KB Articles**: Improve visual quality for documentation
- **Log Screenshots**: Clarify error message screenshots
- **Attachment Processing**: Upscale low-quality images before OCR

## Dependencies

- **Pillow**: `pip install Pillow` (already in requirements.txt)
- **OpenCV** (optional): `pip install opencv-python`
- **NumPy**: `pip install numpy` (already in requirements.txt)
- **SciPy** (for quality assessment): `pip install scipy`
