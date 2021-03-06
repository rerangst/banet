# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/07_web.ipynb (unless otherwise specified).

__all__ = ['ba_split', 'fires2raster', 'process_last']

# Cell
from pathlib import Path
import scipy.io as sio
import pandas as pd
import geopandas as gp
import numpy as np
import rasterio
import rasterio.features
import pdb
import shapely
from shapely.geometry import Polygon
from .core import *
from .geo import  *
from .predict import split_mask
Path.ls = ls

# Cell
def ba_split(io_path:InOutPath, region:Region, min_size=1):
    "Computes burned areas shapefiles."
    files = sorted(io_path.src.ls())
    print(f'Processing {files[-1]}')
    data = sio.loadmat(files[-1])
    fires = split_mask(data['burned'], thr_obj=min_size)

    gpd = gp.GeoDataFrame()
    for fire in fires:
        dates = data['date'].copy()
        dates[fire==0] = np.nan
        start_date = np.nanmin(dates)
        end_date = np.nanmax(dates)
        geoms = list({'properties': {'raster_val': v}, 'geometry': s}
            for i, (s, v) in enumerate(rasterio.features.shapes(fire.astype(np.uint8), transform=region.transform))
        )
        g0 = gp.GeoDataFrame.from_features(geoms, crs={'init' :'epsg:4326'})
        g0['start'] = start_date.astype(int)
        g0['end'] = end_date.astype(int)
        gpd = pd.concat((gpd, g0), axis=0)

    gpd = gpd.loc[gpd.raster_val==1.0].reset_index(drop=True)
    gpd = gp.GeoDataFrame(gpd, crs={'init' :'epsg:4326'})
    gpd['area'] = (gpd.to_crs(epsg=25830).area.values*0.0001).astype(int) # TODO: EPGS for other regions
    gpd = gpd.drop('raster_val', axis=1)
    return gpd, data, fires

def fires2raster(path_save, fires, data):
    "Saves raster files for individual fires."
    for i, f in enumerate(fires):
        args = np.argwhere(f>0)
        lon, lat = R.coords()
        (rmin, cmin), (rmax, cmax) = args.min(0), args.max(0)
        rmax += 1
        cmax += 1
        lat_r = lat[rmin-1:rmax+1]
        lon_r = lon[cmin-1:cmax+1]
        tfm = rasterio.Affine(0.01, 0, lon_r.min(), 0, -0.01, lat_r.max())
        burned_r = data['burned'][rmin-1:rmax+1, cmin-1:cmax+1].copy()
        date_r =  data['date'][rmin-1:rmax+1, cmin-1:cmax+1].copy()
        burned_r[f[rmin-1:rmax+1, cmin-1:cmax+1]==0] = np.nan
        date_r[f[rmin-1:rmax+1, cmin-1:cmax+1]==0] = np.nan

        burned_r = burned_r*255
        burned_r[np.isnan(burned_r)] = 0
        burned_r = burned_r.astype(np.uint16)
        date_r[np.isnan(date_r)] = 0
        date_r = date_r.astype(np.uint16)
        raster = np.array((burned_r, date_r))

        meta = {
            'driver': 'GTiff',
            'dtype': 'uint16',
            'nodata': None,
            'width': burned_r.shape[1],
            'height': burned_r.shape[0],
            'count': 2,
            'crs': rasterio.crs.CRS.from_epsg(4326),
            'transform': tfm
        }

        with rasterio.open(path_save/f'ba_{i}.tif', 'w', **meta) as dst:
            dst.write(raster)

def process_last(iop:InOutPath, region:Region, filter_region:Polygon):
    df, data, fires = ba_split(iop, R)
    df = df.loc[df.within(filter_region)]
    fires = np.array(fires)
    fires = fires[df.index.values.reshape(-1)]
    df = df.reset_index(drop=True)
    fires2raster(iop.dst, fires, data)
    df.to_file(iop.dst/'banet_nrt')