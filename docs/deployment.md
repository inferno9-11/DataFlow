# DataFlow: Cloud Deployment Architecture & Runbooks

This guide provides reproducible deployment specifications for **Azure App Service** and **AWS EC2**.

> [!NOTE]
> Local functionality, unit tests, and database migrations have been fully executed and verified. The cloud deployment templates below are production-ready specifications for cloud environments where credentials are provided.

---

## Part 1: Azure App Service Deployment

DataFlow is packaged as a Linux container and deployed to **Azure App Service (Linux Web App)** backed by managed **Azure Database for PostgreSQL Flexible Server** and **Azure Cache for Redis**.

```mermaid
flowchart LR
    User([Client Traffic]) -->|HTTPS:443| AppService[Azure App Service<br/>Containerized DataFlow]
    AppService -->|VNet Integration| PG[(Azure Database for PostgreSQL<br/>Flexible Server)]
    AppService -->|VNet Integration| Redis[(Azure Cache for Redis<br/>Basic/Standard Tier)]
    AppService -->|Managed Identity| KeyVault[(Azure Key Vault<br/>Secrets Injection)]
```

### 1. Provision Infrastructure via Azure CLI
```bash
# 1. Variables
RESOURCE_GROUP="rg-dataflow-prod"
LOCATION="eastus"
ACR_NAME="acrdataflowprod"
PLAN_NAME="plan-dataflow-prod"
APP_NAME="app-dataflow-api"

# 2. Create Resource Group & Azure Container Registry
az group create --name $RESOURCE_GROUP --location $LOCATION
az acr create --resource-group $RESOURCE_GROUP --name $ACR_NAME --sku Basic --admin-enabled true

# 3. Build & Push Image to ACR
az acr build --registry $ACR_NAME --image dataflow:latest .

# 4. Create App Service Plan (Linux B1 or P1v3)
az appservice plan create \
    --name $PLAN_NAME \
    --resource-group $RESOURCE_GROUP \
    --is-linux \
    --sku B1

# 5. Create Web App for Containers
az webapp create \
    --resource-group $RESOURCE_GROUP \
    --plan $PLAN_NAME \
    --name $APP_NAME \
    --deployment-container-image-name "$ACR_NAME.azurecr.io/dataflow:latest"
```

### 2. Configure Environment & Health Checks
```bash
# Configure application settings (never commit database credentials in source)
az webapp config appsettings set --resource-group $RESOURCE_GROUP --name $APP_NAME --settings \
    ENVIRONMENT="production" \
    PORT=8000 \
    SECRET_KEY="@Microsoft.KeyVault(VaultName=kv-dataflow;SecretName=SecretKey)" \
    DATABASE_URL="postgresql+asyncpg://dataflow_admin:PASSWORD@psql-dataflow.postgres.database.azure.com:5432/dataflow_db?ssl=require" \
    DATABASE_SYNC_URL="postgresql+psycopg://dataflow_admin:PASSWORD@psql-dataflow.postgres.database.azure.com:5432/dataflow_db?ssl=require" \
    REDIS_URL="rediss://:PASSWORD@redis-dataflow.redis.cache.windows.net:6380/0" \
    CELERY_BROKER_URL="rediss://:PASSWORD@redis-dataflow.redis.cache.windows.net:6380/0" \
    CELERY_RESULT_BACKEND="rediss://:PASSWORD@redis-dataflow.redis.cache.windows.net:6380/1" \
    LOG_LEVEL="INFO" \
    LOG_FORMAT="json"

# Configure Azure App Service Health Probe
az webapp config set --resource-group $RESOURCE_GROUP --name $APP_NAME \
    --generic-configurations '{"healthCheckPath": "/health/live"}'
```

---

## Part 2: AWS EC2 Deployment with Docker Compose

For AWS deployments, DataFlow runs on an **Amazon EC2 instance (Ubuntu 22.04 LTS / 24.04 LTS)** using Docker Compose behind an **Nginx HTTPS reverse proxy**.

### 1. Least-Privilege Security Group Rules
Never expose PostgreSQL (5432) or Redis (6379) to the public internet.

| Type | Port Range | Protocol | Source | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **HTTPS** | 443 | TCP | `0.0.0.0/0` | Public client API traffic |
| **HTTP** | 80 | TCP | `0.0.0.0/0` | ACME challenge & HTTP $\to$ HTTPS redirect |
| **SSH** | 22 | TCP | `YOUR_OFFICE_IP/32` | Bastion / Administrator access only |
| **PostgreSQL** | 5432 | TCP | *Docker Internal Network* | Internal database traffic |
| **Redis** | 6379 | TCP | *Docker Internal Network* | Internal broker traffic |

### 2. Host Provisioning Script (User Data / Cloud-Init)
```bash
#!/bin/bash
set -e

# Update packages and install Docker
apt-get update && apt-get upgrade -y
apt-get install -y ca-certificates curl gnupg lsb-release nginx certbot python3-certbot-nginx

# Install Docker Engine
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Setup deployment directory
mkdir -p /opt/dataflow
cd /opt/dataflow
```

### 3. Nginx Reverse Proxy Configuration (`/etc/nginx/sites-available/dataflow`)
```nginx
server {
    listen 80;
    server_name api.dataflow.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $http_x_request_id;
        proxy_connect_timeout 10s;
        proxy_read_timeout 60s;
    }
}
```

Enable SSL via Let's Encrypt:
```bash
certbot --nginx -d api.dataflow.yourdomain.com --non-interactive --agree-tos -m admin@yourdomain.com
```

### 4. Systemd Auto-Restart Service (`/etc/systemd/system/dataflow.service`)
```ini
[Unit]
Description=DataFlow Docker Compose Stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/dataflow
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```
Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable dataflow
sudo systemctl start dataflow
```
