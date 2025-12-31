#!/bin/bash
# Quantum HUB ERP - SSL Setup Script
# Run with: bash setup-ssl.sh your-email@example.com

set -e

DOMAIN="quantumerp.co"
EMAIL="${1:-admin@quantumerp.co}"

echo "======================================"
echo "Quantum HUB ERP - SSL Setup"
echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo "======================================"

cd /home/erp/app

# Create directories
mkdir -p certbot/conf certbot/www

# Step 1: Use initial nginx config (no SSL)
echo "[1/5] Setting up initial nginx configuration..."
cp nginx-initial.conf nginx.conf

# Step 2: Start services with HTTP only
echo "[2/5] Starting services..."
docker compose down 2>/dev/null || true
docker compose up -d db redis backend frontend nginx

# Wait for services to be ready
echo "Waiting for services to start..."
sleep 15

# Step 3: Get SSL certificate
echo "[3/5] Obtaining SSL certificate from Let's Encrypt..."
docker compose run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN" \
    -d "www.$DOMAIN"

# Step 4: Switch to SSL nginx config
echo "[4/5] Switching to SSL configuration..."
cat > nginx.conf << 'NGINX_SSL_CONF'
events {
    worker_connections 1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;

    upstream backend {
        server backend:8000;
    }

    upstream frontend {
        server frontend:3000;
    }

    server {
        listen 80;
        server_name quantumerp.co www.quantumerp.co;

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        location / {
            return 301 https://$host$request_uri;
        }
    }

    server {
        listen 443 ssl http2;
        server_name quantumerp.co www.quantumerp.co;

        ssl_certificate /etc/letsencrypt/live/quantumerp.co/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/quantumerp.co/privkey.pem;

        ssl_session_timeout 1d;
        ssl_session_cache shared:SSL:50m;
        ssl_session_tickets off;

        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
        ssl_prefer_server_ciphers off;

        add_header Strict-Transport-Security "max-age=63072000" always;

        location /api {
            proxy_pass http://backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 86400;
        }

        location /ws {
            proxy_pass http://backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_read_timeout 86400;
        }

        location /health {
            proxy_pass http://backend/health;
        }

        location / {
            proxy_pass http://frontend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
}
NGINX_SSL_CONF

# Step 5: Restart nginx with SSL
echo "[5/5] Restarting nginx with SSL..."
docker compose restart nginx

echo ""
echo "======================================"
echo "SSL Setup Complete!"
echo "======================================"
echo "Your site is now available at:"
echo "  https://quantumerp.co"
echo ""
