import os
import numpy as np
import rasterio
import matplotlib.pyplot as plt
from _paths import PROCESSED_DIR, RAW_DIR

# File Paths
DEM_PATH = str(PROCESSED_DIR / "dem_1km_master.tif")
RADAR_PATH = str(PROCESSED_DIR / "imd_dwr_reflectivity_1km.tif")
GROUND_TRUTH_PATH = str(PROCESSED_DIR / "nrsc_flood_ground_truth_1km.tif")
PRED_RISK_PATH = str(PROCESSED_DIR / "cnn_transformer_flood_risk_map.tif")
OUTPUT_PLOT_PATH = str(PROCESSED_DIR / "rainshield_stage3_dashboard.png")

def plot_rainshield_dashboard():
    print("[+] Generating Stage 3 Visual Inspection Dashboard...")

    # Load spatial rasters
    with rasterio.open(DEM_PATH) as src:
        dem = src.read(1)
    with rasterio.open(RADAR_PATH) as src:
        radar = src.read(1)
    with rasterio.open(GROUND_TRUTH_PATH) as src:
        ground_truth = src.read(1)
    with rasterio.open(PRED_RISK_PATH) as src:
        pred_risk = src.read(1)

    # Set up 2x2 Plot Layout
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    plt.suptitle("RainShield: High-Fidelity Flood Prediction System (Mumbai Grid)", fontsize=16, fontweight='bold')

    # Panel 1: Elevation Model
    im1 = axes[0, 0].imshow(dem, cmap='terrain')
    axes[0, 0].set_title("1. Elevation Baseline (SRTM DEM)", fontsize=12, fontweight='bold')
    plt.colorbar(im1, ax=axes[0, 0], label="Elevation (m)")

    # Panel 2: Radar Reflectivity
    im2 = axes[0, 1].imshow(radar, cmap='turbo')
    axes[0, 1].set_title("2. Weather Radar Intensity (IMD DWR)", fontsize=12, fontweight='bold')
    plt.colorbar(im2, ax=axes[0, 1], label="Reflectivity (dBZ)")

    # Panel 3: Ground Truth Mask
    im3 = axes[1, 0].imshow(ground_truth, cmap='Blues')
    axes[1, 0].set_title("3. Ground Truth Inundation Footprint", fontsize=12, fontweight='bold')
    plt.colorbar(im3, ax=axes[1, 0], label="Inundated Flag (1=Flooded, 0=Dry)")

    # Panel 4: CNN-Transformer Predicted Flood Probability Map
    im4 = axes[1, 1].imshow(pred_risk, cmap='YlOrRd')
    axes[1, 1].set_title("4. Predicted Flood Risk Map (CNN-Transformer)", fontsize=12, fontweight='bold')
    plt.colorbar(im4, ax=axes[1, 1], label="Inundation Risk Probability [0.0 - 1.0]")

    # Formatting adjustments
    for ax in axes.flat:
        ax.set_xlabel("Grid Longitude (1km cells)")
        ax.set_ylabel("Grid Latitude (1km cells)")
        ax.grid(True, linestyle='--', alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUTPUT_PLOT_PATH, dpi=300)
    print(f"[✓] Stage 3 Inspection Dashboard saved to: {OUTPUT_PLOT_PATH}")
    plt.show()

if __name__ == "__main__":
    plot_rainshield_dashboard()