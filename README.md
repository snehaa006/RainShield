---
title: RainShield API
emoji: 🌧️
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 6.27.0
app_file: app.py
pinned: false
---

# RainShield inference API

Heavy-rainfall early warning for the Mumbai suburban 1 km grid — the FastAPI
backend for [RainShield AI](https://github.com/snehaa006/RainShield).

Interactive docs at `/docs`, health at `/health`.

This Space serves the API only; the dashboard is deployed separately and points
at this URL through `VITE_API_BASE`.
