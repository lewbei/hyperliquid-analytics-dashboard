# Hyperliquid Analytics Frontend

React + TypeScript frontend for real-time Hyperliquid perp trading analytics.

## 🚀 Quick Start

### Development

```bash
# Install dependencies
npm install

# Start development server (runs on http://localhost:3000)
npm start
```

### Production Build

```bash
# Build for production
npm run build

# Output will be in ./build directory
```

## 📦 Deployment Options

### Option 1: Serve with FastAPI (Recommended)

Update `backend/api_server.py` to serve the built React app:

```python
from fastapi.staticfiles import StaticFiles

# Add after creating app
app.mount("/", StaticFiles(directory="frontend/build", html=True), name="frontend")
```

Then:
```bash
# Build frontend
cd frontend && npm run build

# Run backend (serves both API and frontend)
python -m uvicorn backend.api_server:app --host 0.0.0.0 --port 8000
```

Access at: `http://localhost:8000`

### Option 2: Nginx (Production)

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    # Serve React app
    location / {
        root /path/to/frontend/build;
        try_files $uri /index.html;
    }

    # Proxy API requests
    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
    }

    # Proxy WebSocket
    location /ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Option 3: Docker (Full Stack)

Update `docker-compose.yml`:

```yaml
services:
  backend:
    # ... existing backend config
    ports:
      - "8000:8000"

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:80"
    depends_on:
      - backend
```

Create `frontend/Dockerfile`:

```dockerfile
# Build stage
FROM node:18-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

## 🔧 Environment Variables

Create `.env` in frontend directory:

```env
REACT_APP_WS_URL=ws://localhost:8000/ws/analytics
REACT_APP_API_URL=http://localhost:8000/api
```

For production, update to your domain:

```env
REACT_APP_WS_URL=wss://yourdomain.com/ws/analytics
REACT_APP_API_URL=https://yourdomain.com/api
```

## 📁 Complete File Structure

You need to create these files in `frontend/src/`:

### `src/index.tsx`
```typescript
import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

### `src/App.tsx`
```typescript
import React from 'react';
import Dashboard from './Dashboard';
import './App.css';

function App() {
  return (
    <div className="App">
      <Dashboard />
    </div>
  );
}

export default App;
```

### `src/Dashboard.tsx`
See the full React dashboard component in the project files.

### `src/useWebSocket.ts`
Custom hook for WebSocket connection with auto-reconnect.

### `src/index.css`
Global styles for the dashboard.

### `src/App.css`
Component-specific styles.

## 🎨 Customization

- **Colors**: Edit CSS variables in `src/index.css`
- **Update Frequency**: Change interval in `useWebSocket.ts`
- **Cards Layout**: Modify grid in `Dashboard.tsx`

## 📊 Features

- ✅ Real-time WebSocket connection
- ✅ Auto-reconnect on disconnect
- ✅ TypeScript type safety
- ✅ Responsive grid layout
- ✅ Status indicators
- ✅ Production-ready build
- ✅ Easy deployment

## 🐛 Troubleshooting

**WebSocket won't connect:**
- Check API server is running on port 8000
- Verify CORS settings in `backend/api_server.py`
- Check browser console for errors

**Build fails:**
- Delete `node_modules` and `package-lock.json`
- Run `npm install` again
- Check Node version (need 16+)

**Blank page after deployment:**
- Check browser console
- Verify API URL in environment variables
- Check nginx/server configuration

## 📚 Next Steps

1. Install dependencies: `npm install`
2. Start backend API server
3. Start frontend: `npm start`
4. Build for production: `npm run build`
5. Deploy built files

For detailed React component code, see the complete files in `src/` directory.
