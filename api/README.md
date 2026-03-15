# Video Frame Extractor API

Extracts unique video frames using SSIM (Structural Similarity Index) comparison.

## Quick Start

```bash
cd api
uv sync
uv run uvicorn frame_extractor.main:app --host 0.0.0.0 --port 8000
```

## API Usage

### Extract Frames

```bash
curl -X POST -F "file=@video.mp4" "http://localhost:8000/extract-frames" -o frames.zip
```

Query parameters:
- `threshold` (float, default 0.95): SSIM similarity threshold (0-1)
- `quality` (int, default 85): JPEG quality (1-100)

## Development

Run tests:

```bash
uv run pytest tests/ -v
```

## Architecture

- **extractor.py**: PyAV video decoding
- **similarity.py**: SSIM-based frame comparison
- **archive.py**: ZIP archive assembly
- **main.py**: FastAPI endpoints
