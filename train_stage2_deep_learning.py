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
MODEL_WEIGHTS_PATH = "./processed_data/rainshield_cnn_transformer.pth"

device = torch.device("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")

# Focal Loss to handle hard spatial boundaries
class BinaryFocalLoss(nn.Module):
    def __init__(self, alpha=0.6, gamma=2.0):
        super(BinaryFocalLoss, self).__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, inputs, targets):
        bce_loss = nn.functional.binary_cross_entropy(inputs, targets, reduction='none')
        pt = torch.exp(-bce_loss)
        focal_loss = self.alpha * (1 - pt) ** self.gamma * bce_loss
        return focal_loss

# Upgraded Hybrid Network with Squeeze-and-Excitation Attention
class RainShieldNetV2(nn.Module):
    def __init__(self, in_channels=10):
        super(RainShieldNetV2, self).__init__()
        
        # 1. Multi-Scale 2D Conv Block
        self.conv1 = nn.Sequential(
            nn.Conv2d(in_channels, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.LeakyReLU(0.1)
        )
        self.conv2 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.LeakyReLU(0.1)
        )
        
        # 2. Channel Attention Block (Squeeze-and-Excitation)
        self.se = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(64, 16, kernel_size=1),
            nn.ReLU(),
            nn.Conv2d(16, 64, kernel_size=1),
            nn.Sigmoid()
        )
        
        # 3. Spatial Transformer Encoder
        encoder_layer = nn.TransformerEncoderLayer(d_model=64, nhead=8, dim_feedforward=256, batch_first=True)
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=3)
        
        # 4. Dense Prediction Head
        self.output_head = nn.Sequential(
            nn.Conv2d(64, 32, kernel_size=1),
            nn.ReLU(),
            nn.Conv2d(32, 1, kernel_size=1),
            nn.Sigmoid()
        )

    def forward(self, x):
        B, C, H, W = x.shape
        c1 = self.conv1(x)
        c2 = self.conv2(c1)
        
        # Apply Channel Attention
        se_weight = self.se(c2)
        c2_attended = c2 * se_weight
        
        # Spatial Transformer Attention
        conv_reshaped = c2_attended.permute(0, 2, 3, 1).reshape(B, H * W, 64)
        trans_out = self.transformer_encoder(conv_reshaped)
        trans_reshaped = trans_out.reshape(B, H, W, 64).permute(0, 3, 1, 2)
        
        out_prob = self.output_head(trans_reshaped)
        return out_prob

def train_deep_learning_model():
    print(f"[+] Using execution device: {device}")
    print("[+] Loading Stage 1 Master Spatial Tensor...")
    data = np.load(TENSOR_PATH)
    
    X_tensor = data["X_tensor"]
    Y_tensor = data["Y_tensor"]
    height, width = Y_tensor.shape
    total_pixels = height * width
    
    # Stratified-style random 80/20 holdout mask
    np.random.seed(42)
    random_indices = np.random.permutation(total_pixels)
    split_idx = int(0.8 * total_pixels)
    
    train_mask = np.zeros(total_pixels, dtype=bool)
    test_mask = np.zeros(total_pixels, dtype=bool)
    train_mask[random_indices[:split_idx]] = True
    test_mask[random_indices[split_idx:]] = True
    
    train_mask_2d = torch.tensor(train_mask.reshape((height, width)), dtype=torch.bool).unsqueeze(0).unsqueeze(0).to(device)
    test_mask_2d = torch.tensor(test_mask.reshape((height, width)), dtype=torch.bool).unsqueeze(0).unsqueeze(0).to(device)

    X_torch = torch.tensor(X_tensor, dtype=torch.float32).unsqueeze(0).to(device)
    Y_torch = torch.tensor(Y_tensor, dtype=torch.float32).unsqueeze(0).unsqueeze(0).to(device)
    
    model = RainShieldNetV2(in_channels=10).to(device)
    criterion = BinaryFocalLoss(alpha=0.6, gamma=2.0)
    optimizer = optim.AdamW(model.parameters(), lr=0.004, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=250)

    print("[+] Training Advanced RainShieldNetV2 with Focal Loss & Channel Attention...")
    model.train()
    best_holdout_auc = 0.0

    for epoch in range(1, 251):
        optimizer.zero_grad()
        output_prob = model(X_torch)
        
        raw_loss = criterion(output_prob, Y_torch)
        masked_loss = (raw_loss * train_mask_2d.float()).sum() / train_mask_2d.sum()
        
        masked_loss.backward()
        optimizer.step()
        scheduler.step()
        
        if epoch % 50 == 0:
            print(f"    Epoch [{epoch:3d}/250] -> Train Focal Loss: {masked_loss.item():.5f}")

    print("[✓] Model Training Complete!")

    # Evaluation on Holdout Set
    model.eval()
    with torch.no_grad():
        pred_prob_torch = model(X_torch)
        pred_prob = pred_prob_torch.squeeze().cpu().numpy()

    y_true_holdout = Y_tensor.flatten()[test_mask]
    y_pred_prob_holdout = pred_prob.flatten()[test_mask]
    y_pred_bin_holdout = (y_pred_prob_holdout >= 0.5).astype(np.float32)

    roc_auc_holdout = roc_auc_score(y_true_holdout, y_pred_prob_holdout)

    print("\n=================== HIGH-ACCURACY HOLDOUT EVALUATION ===================")
    print(f"Unseen Holdout ROC-AUC Score: {roc_auc_holdout:.4f}\n")
    print("Holdout Classification Metrics:")
    print(classification_report(y_true_holdout, y_pred_bin_holdout, target_names=["Dry (0)", "Flooded (1)"]))
    print("========================================================================\n")

    # Save trained model weights
    torch.save(model.state_dict(), MODEL_WEIGHTS_PATH)
    print(f"[✓] Trained Model Weights saved: {MODEL_WEIGHTS_PATH}")

    # Save output GeoTIFF map
    with rasterio.open(MASTER_DEM_PATH) as master_src:
        meta = master_src.meta.copy()

    meta.update({'dtype': 'float32', 'count': 1})
    with rasterio.open(OUTPUT_PRED_RASTER, 'w', **meta) as dst:
        dst.write(pred_prob.astype(np.float32), 1)

    print(f"[✓] Spatial Flood Risk Probability Map saved: {OUTPUT_PRED_RASTER}")

if __name__ == "__main__":
    train_deep_learning_model()