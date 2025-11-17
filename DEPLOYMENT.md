# 🚀 Complete Deployment Guide

## Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│  React Frontend │ <──WS──>│  FastAPI Backend │ <──WS──>│   Hyperliquid   │
│  (Port 3000)    │         │  (Port 8000)     │         │   (Mainnet)     │
└─────────────────┘         └──────────────────┘         └─────────────────┘
                                     │
                                     ▼
                            ┌─────────────────┐
                            │   PostgreSQL    │
                            │  (Digital Ocean)│
                            └─────────────────┘
```

## ✅ What You Have

### Backend (Python + FastAPI)
- ✅ Analytics engine (`backend/api_server.py`)
- ✅ All metrics modules (orderbook, trades, momentum, etc.)
- ✅ WebSocket API endpoint
- ✅ REST API endpoint
- ✅ Database integration ready

### Frontend (React + TypeScript)
- ✅ Package.json configured
- ✅ TypeScript types defined
- ✅ Basic structure created
- ⚠️ Need to complete React components (see below)

## 📝 Setup Steps

### 1. Complete Frontend Setup

Create these files in `frontend/src/`:

**`src/index.tsx`**:
```bash
# Run this in Windows PowerShell or create manually
cd frontend/src
```

Copy the complete code from README.md for:
- `index.tsx`
- `App.tsx`
- `Dashboard.tsx`
- `useWebSocket.ts`
- `index.css`
- `App.css`

### 2. Install Frontend Dependencies

```bash
cd frontend
npm install
```

### 3. Update Backend API to Serve Frontend

Add to `backend/api_server.py` after `app = FastAPI()`:

```python
from fastapi.staticfiles import StaticFiles
import os

# Serve React frontend in production
if os.path.exists("frontend/build"):
    app.mount("/", StaticFiles(directory="frontend/build", html=True), name="frontend")
```

### 4. Update Docker Compose

Edit `docker-compose.yml`:

```yaml
services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.dev
    container_name: scalper-backend-dev
    volumes:
      - ./backend:/app/backend
      - ./tests:/app/tests
      - ./data:/app/data
    environment:
      - ENV=development
      - PYTHONPATH=/app
      - DATABASE_URL=${DATABASE_URL}
    env_file:
      - .env
    ports:
      - "8000:8000"  # Add this!
    command: python -m uvicorn backend.api_server:app --host 0.0.0.0 --port 8000 --reload
    networks:
      - scalper-network

networks:
  scalper-network:
    driver: bridge
```

## 🏃 Running Locally

### Development Mode (Separate Frontend/Backend)

**Terminal 1 - Backend**:
```bash
docker-compose up backend
```

**Terminal 2 - Frontend** (on Windows):
```bash
cd frontend
npm start
```

Frontend: `http://localhost:3000`
Backend API: `http://localhost:8000`

### Production Mode (Single Server)

```bash
# 1. Build frontend
cd frontend
npm run build

# 2. Start backend (serves both)
docker-compose up backend
```

Access everything at: `http://localhost:8000`

## 🌐 Production Deployment

### Option 1: Digital Ocean App Platform

1. **Create App**:
   - Connect GitHub repo
   - Add "Web Service" component

2. **Configure Build**:
   ```yaml
   # Build Command
   cd frontend && npm install && npm run build

   # Run Command
   python -m uvicorn backend.api_server:app --host 0.0.0.0 --port 8080
   ```

3. **Environment Variables**:
   - `DATABASE_URL`: Your PostgreSQL connection string
   - `HYPERLIQUID_NETWORK`: mainnet
   - `HYPERLIQUID_COIN`: SOL

4. **Deploy**: Click "Deploy"

### Option 2: Docker + VPS (DigitalOcean Droplet)

1. **Create Droplet** (Ubuntu 22.04)

2. **Install Docker**:
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
```

3. **Clone & Deploy**:
```bash
git clone <your-repo>
cd signal_only

# Create .env
nano .env
# Add:DATABASE_URL=postgresql://...
# HYPERLIQUID_NETWORK=mainnet
# HYPERLIQUID_COIN=SOL

# Build frontend
cd frontend && npm install && npm run build && cd ..

# Start
docker-compose up -d backend
```

4. **Setup Nginx** (optional, for HTTPS):
```bash
apt install nginx certbot python3-certbot-nginx

# Configure nginx
nano /etc/nginx/sites-available/analytics

# Add:
server {
    server_name yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# Enable & get SSL
ln -s /etc/nginx/sites-available/analytics /etc/nginx/sites-enabled/
certbot --nginx -d yourdomain.com
```

### Option 3: Render.com (Easiest)

1. Connect GitHub repo
2. Create "Web Service"
3. Build: `cd frontend && npm install && npm run build`
4. Start: `pip install -r requirements.txt && uvicorn backend.api_server:app --host 0.0.0.0 --port $PORT`
5. Add environment variables
6. Deploy!

## ✅ Deployment Checklist

- [ ] Frontend built (`npm run build`)
- [ ] Backend API server updated to serve frontend
- [ ] Environment variables configured
- [ ] Database connection tested
- [ ] Port 8000 exposed in docker-compose
- [ ] CORS configured correctly
- [ ] WebSocket endpoint accessible
- [ ] SSL certificate (for production)
- [ ] Domain pointed to server (if using custom domain)

## 🔒 Security for Production

1. **Update CORS** in `backend/api_server.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # Specific domain!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

2. **Use Environment Variables** for secrets
3. **Enable HTTPS** (Let's Encrypt)
4. **Restrict Database Access** (whitelist IPs)

## 📊 Monitoring

Add health check endpoint to `backend/api_server.py`:

```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "analytics_running": analytics_engine is not None,
        "events_processed": analytics_engine.event_count if analytics_engine else 0
    }
```

## 🐛 Common Issues

**"Cannot connect to WebSocket"**:
- Check firewall allows port 8000
- Verify backend is running
- Check browser console for errors

**"Module not found"**:
- Run `pip install -r requirements.txt`
- Rebuild Docker image

**"Database connection failed"**:
- Verify DATABASE_URL in .env
- Check IP is whitelisted in Digital Ocean
- Test connection: `psql $DATABASE_URL`

## 📚 Next Steps

1. ✅ Complete frontend React components (copy from README)
2. ✅ Test locally
3. ✅ Build production version
4. ✅ Choose deployment platform
5. ✅ Deploy!
6. ✅ Add monitoring/logging
7. ✅ Scale as needed

Your full-stack Hyperliquid analytics platform is ready for deployment! 🚀
