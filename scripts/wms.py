#!/bin/python
# -*- coding: utf-8 -*-

import os
import sys
import json
import requests
from osgeo import gdal
from tqdm import tqdm
from loguru import logger


# ---- Hilfsfunktionen ----

def format_logger(logger):
    logger.remove()
    logger.add(sys.stderr, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")
    return logger

def bounds_to_bbox(bounds):
    """Wandelt (xmin, ymin, xmax, ymax) in einen kommagetrennten BBOX-String um"""
    xmin, ymin, xmax, ymax = bounds
    return f"{xmin},{ymin},{xmax},{ymax}"

def image_metadata_to_world_file(metadata):
    """Erstellt eine .jgw Worldfile-Zeichenkette aus Metadaten"""
    xmin = metadata["extent"]["xmin"]
    ymin = metadata["extent"]["ymin"]
    xmax = metadata["extent"]["xmax"]
    ymax = metadata["extent"]["ymax"]
    width = metadata["width"]
    height = metadata["height"]

    x_res = (xmax - xmin) / width
    y_res = (ymax - ymin) / height

    return f"{x_res}\n0.0\n0.0\n{-y_res}\n{xmin}\n{ymax}\n"

class BadFileExtensionException(Exception):
    pass


# ---- Hauptfunktion: eine einzelne Kachel herunterladen ----
def get_jpeg(wms_url, layers, bbox, width, height, filename, srs="EPSG:3857", save_metadata=False, overwrite=True):
    """Holt ein WMS-Bild, speichert es als JPEG (.jpg) und erzeugt ein passendes Worldfile (.jgw)"""

    if not filename.endswith('.jpg'):
        raise BadFileExtensionException("Filename must end with .jpg")

    png_filename = filename.replace('.jpg', '_.png')
    jgw_filename = filename.replace('.jpg', '.jgw')
    md_filename  = filename.replace('.jpg', '.json')
    jpeg_filename = filename

    if save_metadata:
        if not overwrite and os.path.isfile(jpeg_filename) and os.path.isfile(md_filename):
            return None
    else:
        if not overwrite and os.path.isfile(jpeg_filename):
            return None

    params = dict(
        service="WMS",
        version="1.1.1",
        request="GetMap",
        layers=layers,
        format="image/png",
        srs=srs,
        transparent=True,
        styles="",
        bbox=bbox,
        width=width,
        height=height
    )

    xmin, ymin, xmax, ymax = [float(x) for x in bbox.split(',')]
    image_metadata = {
        "width": width,
        "height": height,
        "extent": {
            "xmin": xmin,
            "ymin": ymin,
            "xmax": xmax,
            "ymax": ymax,
            'spatialReference': {'latestWkid': srs.split(':')[1]}
        }
    }

    r = requests.get(wms_url, params=params, allow_redirects=True)

    if r.status_code == 200:
        with open(png_filename, 'wb') as fp:
            fp.write(r.content)

        with open(jgw_filename, 'w') as fp:
            fp.write(image_metadata_to_world_file(image_metadata))

        if save_metadata:
            with open(md_filename, 'w') as fp:
                json.dump(image_metadata, fp)

        try:
            src_ds = gdal.Open(png_filename)
            gdal.Translate(jpeg_filename, src_ds, options=f'-of JPEG -a_srs {srs} -co QUALITY=85')
            src_ds = None
        except Exception as e:
            logger.warning(f"GDAL error: {e}")

        os.remove(png_filename)
        return {jpeg_filename: image_metadata}
    else:
        logger.warning(f"Failed: HTTP {r.status_code} — {r.text[:200]}")
        return {}


# ---- Grid-Erzeugung und Download aller Kacheln ----
def download_wms_grid(wms_url, layers, full_bounds, width, height, tile_px=256,
                      srs="EPSG:3857", output_dir="tiles_output", prefix="tile",
                      save_metadata=False, overwrite=True):
    """
    Teilt ein großes Gebiet in Kacheln und lädt alle einzeln herunter.
    """

    xmin, ymin, xmax, ymax = full_bounds
    os.makedirs(output_dir, exist_ok=True)

    # berechne räumliche Auflösung (Meter pro Pixel)
    x_res = (xmax - xmin) / width
    y_res = (ymax - ymin) / height

    # Kachelgröße in Koordinaten-Einheiten
    tile_size_x = tile_px * x_res
    tile_size_y = tile_px * y_res

    # Anzahl Kacheln
    cols = int((xmax - xmin) / tile_size_x)
    rows = int((ymax - ymin) / tile_size_y)

    logger.info(f"Downloading {rows} × {cols} tiles ({rows * cols} total)...")

    for row in tqdm(range(rows), desc="Rows"):
        for col in range(cols):
            tile_xmin = xmin + col * tile_size_x
            tile_xmax = tile_xmin + tile_size_x
            tile_ymax = ymax - row * tile_size_y
            tile_ymin = tile_ymax - tile_size_y

            bbox = bounds_to_bbox((tile_xmin, tile_ymin, tile_xmax, tile_ymax))
            filename = os.path.join(output_dir, f"{prefix}_{row}_{col}.jpg")

            get_jpeg(
                wms_url=wms_url,
                layers=layers,
                bbox=bbox,
                width=tile_px,
                height=tile_px,
                filename=filename,
                srs=srs,
                save_metadata=save_metadata,
                overwrite=overwrite
            )


# ---- Testlauf ----
if __name__ == '__main__':
    logger = format_logger(logger)
    logger.info("Testing WMS grid download from SITN Neuchâtel...")

    ROOT_URL = "https://sitn.ne.ch/mapproxy95/service"
    LAYERS = "ortho2019"
    SRS = "EPSG:900913"

    # Gesamtbereich, z. B. 1 km²
    FULL_BBOX = (763000, 5968700, 764000, 5969700)

    OUTPUT_DIR = "tiles_output"

    download_wms_grid(
        wms_url=ROOT_URL,
        layers=LAYERS,
        full_bounds=FULL_BBOX,
        width=256 * 4,     # Gesamtbildgröße in Pixeln
        height=256 * 4,    # entspricht 4×4 Tiles
        tile_px=256,
        srs=SRS,
        output_dir=OUTPUT_DIR,
        save_metadata=True,
        overwrite=True
    )

    logger.info("✅ Done. All tiles downloaded.")
