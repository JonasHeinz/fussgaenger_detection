#!/bin/python
# -*- coding: utf-8 -*-

import os
import sys
import json
import requests
from osgeo import gdal
from tqdm import tqdm
from loguru import logger

# ---- Import helper functions ----
try:
    try:
        from helpers.misc import image_metadata_to_world_file, image_metadata_to_world_file, format_logger, BadFileExtensionException
    except ModuleNotFoundError:
        from misc import image_metadata_to_world_file, bounds_to_bbox, format_logger, BadFileExtensionException
except Exception as e:
    logger.error(f"Could not import some dependencies. Exception: {e}")
    sys.exit(1)

logger = format_logger(logger)


# ---- Hauptfunktion zum Abrufen eines WMS-Bildes ----
def get_jpeg(wms_url, layers, bbox, width, height, filename, srs="EPSG:3857", save_metadata=False, overwrite=True):
    """
    Holt ein WMS-Bild, speichert es als JPEG (.jpg) und erzeugt ein passendes Worldfile (.jgw)
    """

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

    # ---- Parameter für WMS-Request ----
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

    # ---- Bildmetadaten erzeugen ----
    image_metadata = {
        "width": width,
        "height": height,
        "extent": {
            "xmin": xmin,
            "ymin": ymin,
            "xmax": xmax,
            "ymax": ymax,
            'spatialReference': {
                'latestWkid': srs.split(':')[1]
            }
        }
    }

    # ---- WMS-Bild abrufen ----
    r = requests.get(wms_url, params=params, allow_redirects=True)

    if r.status_code == 200:
        # PNG speichern
        with open(png_filename, 'wb') as fp:
            fp.write(r.content)

        # Worldfile (.jgw) aus Metadaten erstellen
        jgw = image_metadata_to_world_file(image_metadata)
        with open(jgw_filename, 'w') as fp:
            fp.write(jgw)

        # Metadaten speichern (optional)
        if save_metadata:
            with open(md_filename, 'w') as fp:
                json.dump(image_metadata, fp)

        # PNG → JPEG umwandeln + Geo-Referenz
        try:
            src_ds = gdal.Open(png_filename)
            gdal.Translate(
                jpeg_filename,
                src_ds,
                options=f'-of JPEG -a_srs {srs} -co QUALITY=85'
            )
            src_ds = None
        except Exception as e:
            logger.warning(f"Exception in the 'get_jpeg' function: {e}")

        # Temporäre Dateien löschen
        os.remove(png_filename)

        return {jpeg_filename: image_metadata}

    else:
        logger.warning(f"Failed to get image from WMS: HTTP Status Code = {r.status_code}, received text = '{r.text}'")
        return {}


# ---- Erzeuge Jobs für mehrere Tiles ----
def get_job_dict(tiles_gdf, wms_url, layers, width, height, img_path, srs, save_metadata=False, overwrite=True):
    job_dict = {}

    for tile in tqdm(tiles_gdf.itertuples(), total=len(tiles_gdf)):
        img_filename = os.path.join(img_path, f'{tile.z}_{tile.x}_{tile.y}.jpg')
        bbox = bounds_to_bbox(tile.geometry.bounds)

        job_dict[img_filename] = {
            'wms_url': wms_url,
            'layers': layers,
            'bbox': bbox,
            'width': width,
            'height': height,
            'filename': img_filename,
            'srs': srs,
            'save_metadata': save_metadata,
            'overwrite': overwrite
        }

    return job_dict


# ---- Testlauf ----
if __name__ == '__main__':
    print("Testing using Neuchâtel Canton's WMS (JPEG output)...")

    ROOT_URL = "https://sitn.ne.ch/mapproxy95/service"
    BBOX = "763453.0385123404,5969120.412845984,763605.9125689107,5969273.286902554"
    WIDTH = 256
    HEIGHT = 256
    LAYERS = "ortho2019"
    SRS = "EPSG:900913"
    OUTPUT_IMG = 'test.jpg'
    OUTPUT_DIR = 'test_output'

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    out_filename = os.path.join(OUTPUT_DIR, OUTPUT_IMG)

    outcome = get_jpeg(
        ROOT_URL,
        LAYERS,
        bbox=BBOX,
        width=WIDTH,
        height=HEIGHT,
        filename=out_filename,
        srs=SRS,
        save_metadata=True
    )

    if outcome != {}:
        print(f'✅ Done. An image was generated: {out_filename}')
