"""The RainShield CNN + spatial-transformer network.

This definition must stay byte-compatible with
processed_data/rainshield_cnn_transformer.pth — the checkpoint is loaded with
strict=True, so any change to layer names or shapes breaks serving. The
training-side copy lives in backend/pipeline/stage2_train.py.

The network consumes the RAW tensor in physical units (metres, people/km2, mm,
Kelvin, dBZ), not the MinMax-scaled matrix; the leading BatchNorm absorbs the
differing channel magnitudes. Feeding scaled input produces garbage.
"""

from __future__ import annotations

import torch
import torch.nn as nn


class RainShieldNet(nn.Module):
    def __init__(self, in_channels: int = 10, nhead: int = 4):
        super().__init__()

        self.conv1 = nn.Sequential(
            nn.Conv2d(in_channels, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
        )
        self.conv2 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
        )

        # Squeeze-and-excitation: re-weights channels using global context.
        self.se = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(64, 16, kernel_size=1),
            nn.ReLU(),
            nn.Conv2d(16, 64, kernel_size=1),
            nn.Sigmoid(),
        )

        # Spatial self-attention over the flattened 45 x 39 cell sequence.
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=64, nhead=nhead, dim_feedforward=256, batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=3)

        self.output_head = nn.Sequential(
            nn.Conv2d(64, 32, kernel_size=1),
            nn.ReLU(),
            nn.Conv2d(32, 1, kernel_size=1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, _, h, w = x.shape
        feats = self.conv2(self.conv1(x))
        feats = feats * self.se(feats)
        seq = feats.permute(0, 2, 3, 1).reshape(b, h * w, 64)
        seq = self.transformer_encoder(seq)
        seq = seq.reshape(b, h, w, 64).permute(0, 3, 1, 2)
        return self.output_head(seq)
