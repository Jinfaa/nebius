# Deployment Guide - Video Frame Extractor API

## Prerequisites

- Python 3.11+
- `uv` package manager
- `ffmpeg` (for tests; optional for production)

## Local Development

### 1. Setup
```bash
cd api
uv sync
```

### 2. Run Server
```bash
uv run uvicorn frame_extractor.main:app --host 0.0.0.0 --port 8000
```

### 3. Access API
- **Interactive Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

### 4. Test
```bash
# Run all tests
uv run pytest tests/test_api.py -v

# Run verification
uv run python3 verify.py
```

## Production Deployment

### Using Gunicorn (Recommended)
```bash
# Add gunicorn
uv add gunicorn

# Run with 4 workers
uv run gunicorn frame_extractor.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 300
```

### Using Docker
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install ffmpeg for testing (optional)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy project
COPY . .

# Install dependencies
RUN uv sync --frozen

# Expose port
EXPOSE 8000

# Run server
CMD ["uv", "run", "uvicorn", "frame_extractor.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Using systemd
```ini
[Unit]
Description=Video Frame Extractor API
After=network.target

[Service]
Type=notify
User=www-data
WorkingDirectory=/opt/frame-extractor
ExecStart=/opt/frame-extractor/.venv/bin/gunicorn \
  frame_extractor.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind unix:/tmp/frame_extractor.sock
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Environment Configuration

### Environment Variables
```bash
# Optional: Configure from environment
export FRAME_EXTRACTOR_HOST=0.0.0.0
export FRAME_EXTRACTOR_PORT=8000
export FRAME_EXTRACTOR_WORKERS=4
export FRAME_EXTRACTOR_TIMEOUT=300
```

### Resource Requirements

| Component | Recommendation |
|-----------|----------------|
| CPU | 2+ cores |
| RAM | 2GB minimum (512MB per worker) |
| Temp Disk | 10GB (for video processing) |
| Max Upload | Configure at reverse proxy |

## Performance Tuning

### 1. Worker Count
```
workers = (2 × cores) + 1
```

### 2. Timeouts
- Default: 300s (5 minutes)
- Adjust based on video sizes: `timeout = (max_video_size_GB × 100) + 60`

### 3. Memory Limits
- Each worker processes one video at a time
- Peak memory: ~500MB per worker

### 4. Temp Directory
```bash
# Use fast SSD for temp processing
export TMPDIR=/fast-ssd/tmp
```

## Health Monitoring

### Health Check Endpoint
```bash
curl -s http://localhost:8000/health | jq .
# Output: {"status":"ok"}
```

### Monitoring Metrics to Track
- Request duration (frame extraction time)
- Frame count per video
- Error rates (invalid videos, upload failures)
- Disk usage (temp directory growth)

## Security Considerations

### 1. File Upload Limits
Configure at reverse proxy:
```nginx
client_max_body_size 1G;  # Adjust as needed
```

### 2. Rate Limiting (Using nginx)
```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/m;
limit_req zone=api;
```

### 3. HTTPS/TLS
Deploy behind reverse proxy (nginx/Apache) with SSL

### 4. Input Validation
- File type verification (magic bytes, not just extension)
- Video duration limits (avoid resource exhaustion)
- Output validation (all frames are valid JPEG)

## Troubleshooting

### Issue: "No such file or directory" (FFmpeg)
**Solution**: Ensure ffmpeg is installed
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
apt-get install ffmpeg

# Docker: Already included in Dockerfile
```

### Issue: Out of Memory
**Solution**:
- Reduce worker count: `--workers 2`
- Increase swap: `dd if=/dev/zero of=/swapfile bs=1M count=4096`
- Limit video size at reverse proxy

### Issue: Slow Frame Extraction
**Solution**:
- Frames are downscaled to 512px before SSIM (already optimized)
- Consider reducing JPEG quality if CPU-bound
- Use SSD for temp directory

### Issue: Incomplete ZIP Files
**Solution**:
- Check reverse proxy timeout settings
- Increase server timeout: `--timeout 600`
- Monitor disk space during processing

## Rollback Procedure

```bash
# Keep previous version
git tag -a v1.0 -m "Production release"

# To rollback
git checkout v1.0
uv sync
uv run uvicorn frame_extractor.main:app ...
```

## Monitoring Script

```bash
#!/bin/bash
# Check API health
curl -s http://localhost:8000/health || echo "API DOWN"

# Check worker processes
ps aux | grep uvicorn

# Check disk usage
du -sh /tmp/frame_extractor* 2>/dev/null | head -5

# Check temp file cleanup
ls -lt /tmp/tmp* 2>/dev/null | head -5
```

## Support & Maintenance

- Check logs: `journalctl -u frame-extractor -f`
- Clean temp files: `rm -rf /tmp/tmp*` (optional, auto-cleaned after response)
- Monitor CPU/RAM with: `top`, `htop`, or cloud provider dashboard
