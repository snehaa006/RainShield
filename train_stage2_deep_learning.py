import os
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import rasterio
from sklearn.metrics import roc_auc_score, classification_report

TENSOR_PATH = "./processed_data/rainshield_stage1_tensor.npz"
MASTER_DEM_PATH = "./processed_data/dem_1km_master.tif"
OUTPUT_PRED_RASTER = "./processed_data/cnn_transformer_flood_risk_map.tif"

# PyTorch Device Configuration
device = torch.device("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")

# Define Hybrid CNN-Transformer Architecture for Spatial Flood Risk Prediction
class RainShieldNet(nn.Module):
    def __init__(self, in_channels=10):
        super(RainShieldNet, self).__init__()
        
        # 1. Spatial Feature Extractor (2D Convolutional Layers)
        self.conv_block = nn.Sequential(
            nn.Conv2d(in_channels, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU()
        )
        
        # 2. Spatial Self-Attention (Transformer Encoder Layer)
        encoder_layer = nn.TransformerEncoderLayer(d_model=64, nhead=4, dim_feedforward=128, batch_first=True)
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=2)
        
        # 3. Dense Flood Risk Head
        self.output_head = nn.Sequential(
            nn.Conv2d(64, 32, kernel_size=1),
            nn.ReLU(),
            nn.Conv2d(32, 1, kernel_size=1),
            nn.Sigmoid()
        )

    def forward(self, x):
        # x shape: (Batch, 10, H, W)
        B, C, H, W = x.shape
        
        # Pass through Conv Layers -> (B, 64, H, W)
        conv_feats = self.conv_block(x)
        
        # Reshape for Transformer: (B, 64, H, W) -> (B, H*W, 64)
        conv_reshaped = conv_feats.permute(0, 2, 3, 1).reshape(B, H * W, 64)
        
        # Pass through Transformer Encoder
        trans_out = self.transformer_encoder(conv_reshaped)
        
        # Reshape back to spatial grid: (B, H*W, 64) -> (B, 64, H, W)
        trans_reshaped = trans_out.reshape(B, H, W, 64).permute(0, 3, 1, 2)
        
        # Compute per-pixel flood probability mask: (B, 1, H, W)
        out_prob = self.output_head(trans_reshaped)
        return out_prob

def train_deep_learning_model():
    print(f"[+] Using execution device: {device}")
    print("[+] Loading Stage 1 Master Spatial Tensor...")
    data = np.load(TENSOR_PATH)
    
    X_tensor = data["X_tensor"]  # Shape: (10, 45, 39)
    Y_tensor = data["Y_tensor"]  # Shape: (45, 39)
    
    # Add Batch dimension: (1, 10, 45, 39) and (1, 1, 45, 39)
    X_torch = torch.tensor(X_tensor, dtype=torch.float32).unsqueeze(0).to(device)
    Y_torch = torch.tensor(Y_tensor, dtype=torch.float32).unsqueeze(0).unsqueeze(0).to(device)
    
    # Initialize Model, Loss Function, and Adam Optimizer
    model = RainShieldNet(in_channels=10).to(device)
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.005)

    print("[+] Training CNN-Transformer Hybrid Network over 3D Spatial Tensor...")
    model.train()
    for epoch in range(1, 151):
        optimizer.zero_grad()
        output_prob = model(X_torch)
        loss = criterion(output_prob, Y_torch)
        loss.backward()
        optimizer.step()
        
        if epoch % 30 == 0:
            print(f"    Epoch [{epoch:3d}/150] -> Binary Cross-Entropy Loss: {loss.item():.5f}")

    print("[✓] Deep Learning Model Training Complete!")

    # Model Evaluation
    model.eval()
    with torch.no_grad():
        pred_prob_torch = model(X_torch)
        pred_prob = pred_prob_torch.squeeze().cpu().numpy()

    y_true_flat = Y_tensor.flatten()
    y_pred_prob_flat = pred_prob.flatten()
    y_pred_bin_flat = (y_pred_prob_flat >= 0.5).astype(np.float32)

    roc_auc = roc_auc_score(y_true_flat, y_pred_prob_flat)

    print("\n=================== CNN-TRANSFORMER MODEL REPORT ===================")
    print(f"ROC-AUC Score: {roc_auc:.4f}\n")
    print("Classification Metrics:")
    print(classification_report(y_true_flat, y_pred_bin_flat, target_names=["Dry (0)", "Flooded (1)"]))
    print("====================================================================\n")

    # Export Spatial Risk Probability Map to GeoTIFF
    print("[+] Reconstructing Spatial Risk Probability Map...")
    with rasterio.open(MASTER_DEM_PATH) as master_src:
        meta = master_src.meta.copy()

    meta.update({'dtype': 'float32', 'count': 1})
    with rasterio.open(OUTPUT_PRED_RASTER, 'w', **meta) as dst:
        dst.write(pred_prob.astype(np.float32), 1)

    print(f"[✓] CNN-Transformer Flood Risk Map saved: {OUTPUT_PRED_RASTER}")

if __name__ == "__main__":
    train_deep_learning_model()