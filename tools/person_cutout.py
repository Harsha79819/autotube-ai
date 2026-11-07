#!/usr/bin/env python3
"""
tools/person_cutout.py - Apple Neural Engine Person Segmentation & Cutout Extractor

Extracts clean, transparent RGBA cutouts of people/contestants with fine hair feathering:
- Leverages macOS Vision framework (`VNGeneratePersonSegmentationRequest`) with Apple Neural Engine acceleration.
- Takes standard JPEG/PNG portraits and produces professional alpha-channeled cutouts in <1 second.
- Caches cutouts to disk in `data/cache/cutout_cache/`.
- Used for high-CTR Prasad Tech in Telugu style thumbnails and smart creator video overlays.
"""

import os
import sys
import shutil
import hashlib
import tempfile
import subprocess
from pathlib import Path
from typing import Optional
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache" / "cutout_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SWIFT_SEGMENTATION_SCRIPT = """
import Foundation
import Vision
import AppKit
import CoreImage

let args = CommandLine.arguments
guard args.count >= 3 else {
    exit(1)
}

let inputPath = args[1]
let outputPath = args[2]

let url = URL(fileURLWithPath: inputPath)
guard let img = NSImage(contentsOf: url),
      let cgImg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    exit(1)
}

let request = VNGeneratePersonSegmentationRequest()
request.qualityLevel = .accurate
request.outputPixelFormat = kCVPixelFormatType_OneComponent8

let handler = VNImageRequestHandler(cgImage: cgImg, options: [:])
do {
    try handler.perform([request])
} catch {
    exit(1)
}

guard let maskPixelBuffer = request.results?.first?.pixelBuffer else {
    exit(1)
}

let ciMask = CIImage(cvPixelBuffer: maskPixelBuffer)
let ciImage = CIImage(cgImage: cgImg)

// Scale mask to original image dimensions
let scaleX = CGFloat(cgImg.width) / ciMask.extent.width
let scaleY = CGFloat(cgImg.height) / ciMask.extent.height
let scaledMask = ciMask.transformed(by: CGAffineTransform(scaleX: scaleX, y: scaleY))

// Blend image with transparent canvas
guard let filter = CIFilter(name: "CIBlendWithMask") else {
    exit(1)
}
filter.setValue(ciImage, forKey: kCIInputImageKey)
filter.setValue(CIImage.empty(), forKey: kCIInputBackgroundImageKey)
filter.setValue(scaledMask, forKey: kCIInputMaskImageKey)

guard let outputCI = filter.outputImage else {
    exit(1)
}

let context = CIContext()
guard let outputCG = context.createCGImage(outputCI, from: ciImage.extent) else {
    exit(1)
}

let rep = NSBitmapImageRep(cgImage: outputCG)
guard let pngData = rep.representation(using: .png, properties: [:]) else {
    exit(1)
}

try? pngData.write(to: URL(fileURLWithPath: outputPath))
"""

_swift_script_path: Optional[str] = None


def _get_swift_script() -> str:
    global _swift_script_path
    if _swift_script_path and os.path.exists(_swift_script_path):
        return _swift_script_path
    tmp = tempfile.NamedTemporaryFile(suffix=".swift", delete=False, mode="w", encoding="utf-8")
    tmp.write(SWIFT_SEGMENTATION_SCRIPT)
    tmp.close()
    _swift_script_path = tmp.name
    return _swift_script_path


def extract_person_cutout(
    image_path: Path,
    output_path: Optional[Path] = None,
) -> Optional[Path]:
    """
    Extracts an alpha-transparent person cutout from image_path using macOS Vision Neural Engine.
    Returns Path to transparent PNG if successful, or None.
    """
    inp = Path(image_path)
    if not inp.exists() or inp.stat().st_size < 1000:
        return None

    # Check if already transparent RGBA PNG
    try:
        with Image.open(inp) as test_im:
            if test_im.mode == "RGBA":
                # Check if alpha channel actually has transparency
                extrema = test_im.getextrema()
                if len(extrema) == 4 and extrema[3][0] < 250:
                    return inp
    except Exception:
        pass

    # Disk cache key based on file content MD5
    try:
        file_hash = hashlib.md5(inp.read_bytes()).hexdigest()
    except Exception:
        file_hash = hashlib.md5(str(inp).encode("utf-8")).hexdigest()

    cached_cutout = CACHE_DIR / f"cutout_{file_hash}.png"
    dest = Path(output_path) if output_path else cached_cutout

    if cached_cutout.exists() and cached_cutout.stat().st_size > 2000:
        if dest != cached_cutout:
            shutil.copyfile(cached_cutout, dest)
        return dest

    if sys.platform != "darwin" or not shutil.which("swift"):
        return None

    script_path = _get_swift_script()
    temp_dest = CACHE_DIR / f"temp_{file_hash}.png"

    try:
        cmd = ["swift", script_path, str(inp), str(temp_dest)]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        if temp_dest.exists() and temp_dest.stat().st_size > 2000:
            os.replace(temp_dest, cached_cutout)
            if dest != cached_cutout:
                shutil.copyfile(cached_cutout, dest)
            return dest
    except Exception as e:
        print(f"⚠️ Person segmentation notice for {inp.name}: {e}")
        temp_dest.unlink(missing_ok=True)

    return None


if __name__ == "__main__":
    if len(sys.argv) > 1:
        res = extract_person_cutout(Path(sys.argv[1]))
        print(f"Cutout result: {res}")
