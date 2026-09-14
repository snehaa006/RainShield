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
        B, C, H, W = x.shape
        conv_feats = self.conv_block(x)
        conv_reshaped = conv_feats.permute(0, 2, 3, 1).reshape(B, H * W, 64)
        trans_out = self.transformer_encoder(conv_reshaped)
        trans_reshaped = trans_out.reshape(B, H, W, 64).permute(0, 3, 1, 2)
        out_prob = self.output_head(trans_reshaped)
        return out_prob

def train_deep_learning_model():
    print(f"[+] Using execution device: {device}")
    print("[+] Loading Stage 1 Master Spatial Tensor...")
    data = np.load(TENSOR_PATH)
    
    X_tensor = data["X_tensor"]  # Shape: (10, 45, 39)
    Y_tensor = data["Y_tensor"]  # Shape: (45, 39)
    
    height, width = Y_tensor.shape
    total_pixels = height * width
    
    # Generate reproducible 80% Train / 20% Spatial Holdout Mask
    np.random.seed(42)
    random_indices = np.random.permutation(total_pixels)
    split_idx = int(0.8 * total_pixels)
    
    train_flat_indices = random_indices[:split_idx]
    test_flat_indices = random_indices[split_idx:]
    
    train_mask = np.zeros(total_pixels, dtype=bool)
    test_mask = np.zeros(total_pixels, dtype=bool)
    train_mask[train_flat_indices] = True
    test_mask[test_flat_indices] = True
    
    train_mask_2d = torch.tensor(train_mask.reshape((height, width)), dtype=torch.bool).unsqueeze(0).unsqueeze(0).to(device)
    test_mask_2d = torch.tensor(test_mask.reshape((height, width)), dtype=torch.bool).unsqueeze(0).unsqueeze(0).to(device)

    print(f"[✓] Created Spatial Loss Masks: {split_idx} Train Cells (80%), {total_pixels - split_idx} Holdout Evaluation Cells (20%)")

    # Format Tensors
    X_torch = torch.tensor(X_tensor, dtype=torch.float32).unsqueeze(0).to(device)
    Y_torch = torch.tensor(Y_tensor, dtype=torch.float32).unsqueeze(0).unsqueeze(0).to(device)
    
    # Model Setup
    model = RainShieldNet(in_channels=10).to(device)
    criterion = nn.BCELoss(reduction='none') # Compute element-wise loss for spatial masking
    optimizer = optim.Adam(model.parameters(), lr=0.003)

    print("[+] Training CNN-Transformer with Spatial Masking...")
    model.train()
    for epoch in range(1, 151):
        optimizer.zero_grad()
        output_prob = model(X_torch)
        
        # Calculate raw spatial loss
        raw_loss = criterion(output_prob, Y_torch)
        
        # Mask loss to train ONLY on 80% training cells
        masked_loss = (raw_loss * train_mask_2d.float()).sum() / train_mask_2d.sum()
        
        masked_loss.backward()
        optimizer.step()
        
        if epoch % 30 == 0:
            print(f"    Epoch [{epoch:3d}/150] -> Train Mask BCE Loss: {masked_loss.item():.5f}")

    print("[✓] Model Training Complete!")

    # Honest Evaluation on 20% Unseen Spatial Holdout Cells
    model.eval()
    with torch.no_grad():
        pred_prob_torch = model(X_torch)
        pred_prob = pred_prob_torch.squeeze().cpu().numpy()

    # Extract ONLY holdout test pixels
    y_true_holdout = Y_tensor.flatten()[test_mask]
    y_pred_prob_holdout = pred_prob.flatten()[test_mask]
    y_pred_bin_holdout = (y_pred_prob_holdout >= 0.5).astype(np.float32)

    roc_auc_holdout = roc_auc_score(y_true_holdout, y_pred_prob_holdout)

    print("\n=================== HONEST HOLDOUT EVALUATION (20% UNSEEN CELLS) ===================")
    print(f"Unseen Holdout ROC-AUC Score: {roc_auc_holdout:.4f}\n")
    print("Holdout Classification Metrics:")
    print(classification_report(y_true_holdout, y_pred_bin_holdout, target_names=["Dry (0)", "Flooded (1)"]))
    print("===================================================================================\n")

    # Save reconstructed map
    with rasterio.open(MASTER_DEM_PATH) as master_src:
        meta = master_src.meta.copy()

    meta.update({'dtype': 'float32', 'count': 1})
    with rasterio.open(OUTPUT_PRED_RASTER, 'w', **meta) as dst:
        dst.write(pred_prob.astype(np.float32), 1)

    print(f"[✓] Spatial Flood Risk Probability Map saved: {OUTPUT_PRED_RASTER}")

if __name__ == "__main__":
    train_deep_learning_model()