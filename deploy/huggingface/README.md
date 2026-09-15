---
title: RainShield API
emoji: 🌧️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# RainShield inference API

Heavy-rainfall early warning for the Mumbai suburban 1 km grid — the FastAPI
backend for [RainShield AI](https://github.com/snehaa006/RainShield).

Interactive docs at `/docs`, health at `/health`.

This Space serves the API only; the dashboard is deployed separately and points
at this URL through `VITE_API_BASE`.
