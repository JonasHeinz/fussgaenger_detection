#!/bin/python
# -*- coding: utf-8 -*-

import os
import json
import requests
from osgeo import gdal
from tqdm import tqdm

# ---- Einfaches Logging ----
def log(msg, level="INFO"):
    print(f"[{level}] {msg}")

# ---- Wandelt Bildmetadaten in Worldfile (.jgw) um ----
def image_metadata_to_world_file(metadata):
    xmin = metadata["extent"]["xmin"]
    ymin = metadata["extent"]["ymin"]
    xmax = metadata["extent"]["xmax"]
    ymax = metadata["extent"]["ymax"]
    width = metadata["width"]
    height = metadata["height"]

    x_res = (xmax - xmin) / width
    y_res = (ymax - ymin) / height

    # Worldfile (6 Zeilen)
    jgw = f"{x_res}\n0.0\n0.0\n{-y_res}\n{xmin}\n{ymax}\n"
    return jgw

# ---- BBOX in String-Format umwandeln ----
def bounds_to_bbox(bounds):
    xmin, ymin, xmax, ymax = bounds
    return f"{xmin},{ymin},{xmax},{ymax}"

# ---- Hauptfunktion: WMS-Bild holen und speichern ----
def get_jpeg(wms_url, layers, bbox, width, height, filename, srs="EPSG:3857", save_metadata=False, overwrite=True):
    if not filename.endswith('.jpg'):
        raise ValueError("Filename must end with .jpg")

    png_filename = filename.replace('.jpg', '_.png')
    jgw_filename = filename.replace('.jpg', '.jgw')
    md_filename  = filename.replace('.jpg', '.json')

    if not overwrite and os.path.exists(filename):
        log(f"Skipping existing file: {filename}")
        return None

    params = dict(
        service="WMS",
        version="1.1.1",
        request="GetMap",
        layers=layers,
        format="image/png",
        srs=srs,
        transparent=True,
        bbox=bbox,
        width=width,
        height=height
    )

    xmin, ymin, xmax, ymax = [float(x) for x in bbox.split(',')]
    image_metadata = {
        "width": width,
        "height": height,
        "extent": {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax, "srs": srs}
    }

    r = requests.get(wms_url, params=params)
    if r.status_code != 200:
        log(f"Request failed ({r.status_code}): {r.text[:200]}", "ERROR")
        return None

    # PNG speichern
    with open(png_filename, 'wb') as f:
        f.write(r.content)

    # Worldfile schreiben
    with open(jgw_filename, 'w') as f:
        f.write(image_metadata_to_world_file(image_metadata))

    # Metadaten speichern
    if save_metadata:
        with open(md_filename, 'w') as f:
            json.dump(image_metadata, f, indent=2)

    # PNG → JPEG umwandeln
    try:
        ds = gdal.Open(png_filename)
        gdal.Translate(filename, ds, options=f'-of JPEG -a_srs {srs} -co QUALITY=85')
        ds = None
    except Exception as e:
        log(f"GDAL error: {e}", "WARNING")

    os.remove(png_filename)
    return filename

# ---- Beispieltest ----
if __name__ == "__main__":
    ROOT_URL = "https://sitn.ne.ch/mapproxy95/service"
    BBOX = "763453.0385123404,5969120.412845984,763605.9125689107,5969273.286902554"
    WIDTH, HEIGHT = 256, 256
    LAYERS = "ortho2019"
    SRS = "EPSG:900913"
    OUTPUT_DIR = "test_output"
    OUTPUT_IMG = os.path.join(OUTPUT_DIR, "test.jpg")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    log("Downloading WMS image...")
    result = get_jpeg(ROOT_URL, LAYERS, BBOX, WIDTH, HEIGHT, OUTPUT_IMG, SRS, save_metadata=True)
    if result:
        log(f"✅ Done. Saved: {result}")
