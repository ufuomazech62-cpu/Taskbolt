# Taskbolt SaaS - Multi-Tenant Architecture

A complete transformation of CoPaw from a single-user personal assistant to a multi-tenant SaaS platform with secure, scalable infrastructure on Google Cloud Platform.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TASKBOLT SAAS ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐         ┌──────────────────────────────────────────┐  │
│  │    FRONTEND      │         │            BACKEND SERVICES              │  │
│  │    (React)       │         │                                          │  │
│  │                  │         │  ┌────────────────────────────────────┐  │  │
│  │  ┌────────────┐  │         │  │     Firebase Auth Middleware      │  │  │
│  │  │  Firebase  │  │────────▶│  │     - Token Verification         │  │  │
│  │  │  Hosting   │  │         │  │     - Tenant Context Injection   │  │  │
│  │  └────────────┘  │         │  └────────────────────────────────────┘  │  │
│  │                  │         │                    │                      │  │
│  │  ┌────────────┐  │         │                    ▼                      │  │
│  │  │  React +   │  │         │  ┌────────────────────────────────────┐  │  │
│  │  │  TypeScript│  │         │  │        FastAPI Backend            │  │  │
│  │  │  Tailwind  │  │         │  │                                    │  │  │
│  │  │  Zustand   │  │         │  │  ┌──────────────┐ ┌─────────────┐ │  │  │
│  │  └────────────┘  │         │  │  │ Agent API    │ │ Chat API    │ │  │  │
│  │                  │         │  │  └──────────────┘ └─────────────┘ │  │  │
│  └──────────────────┘         │  │                                    │  │  │
│                               │  │  ┌──────────────┐ ┌─────────────┐ │  │  │
│                               │  │  │ Billing API  │ │ Usage API   │ │  │  │
│                               │  │  └──────────────┘ └─────────────┘ │  │  │
│                               │  │                                    │  │  │
│                               │  └────────────────────────────────────┘  │  │
│                               │                    │                      │  │
│                               │         ┌─────────┴─────────┐            │  │
│                               │         ▼                   ▼            │  │
│                               │  ┌─────────────┐    ┌──────────────┐    │  │
│                               │  │  Cloud SQL  │    │ Secret       │    │  │
│                               │  │  PostgreSQL │    │ Manager      │    │  │
│                               │  │  (Prisma)   │    │ (API Keys)   │    │  │
│                               │  └─────────────┘    └──────────────┘    │  │
│                               │                                          │  │
│                               └──────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         EXTERNAL SERVICES                            │  │
│  │                                                                      │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐     │  │
│  │  │  Firebase  │  │   Stripe   │  │    LLM     │  │   Redis    │     │  │
│  │  │    Auth    │  │  Billing   │  │ Providers  │  │  (Cache)   │     │  │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                       GOOGLE CLOUD PLATFORM                          │  │
│  │                                                                      │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐     │  │
│  │  │ Cloud Run  │  │ Cloud SQL  │  │  Cloud     │  │  Cloud     │     │  │
│  │  │ (Backend)  │  │   (DB)     │  │  Storage   │  │  Secrets   │     │  │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. Authentication (Firebase Auth)
- **User Management**: Registration, login, password reset
- **OAuth Providers**: Google, GitHub, etc.
- **Custom Claims**: Tenant ID and role embedded in JWT
- **Session Management**: Secure token refresh

### 2. Multi-Tenancy
- **Tenant Isolation**: Every data query scoped to tenant
- **Role-Based Access**: Owner, Admin, Member, Viewer
- **API Keys**: Per-tenant programmatic access
- **Audit Logging**: All actions tracked per tenant

### 3. Database (Cloud SQL + Prisma)
- **PostgreSQL**: Scalable relational database
- **Prisma ORM**: Type-safe database access
- **Automatic Migrations**: Version-controlled schema changes
- **Connection Pooling**: Efficient resource usage

### 4. Rate Limiting
- **Per-Tenant Quotas**: Based on subscription plan
- **Redis Backend**: Distributed rate limiting
- **Graceful Degradation**: Fallback to in-memory

### 5. Billing (Stripe)
- **Subscription Plans**: Free, Starter, Professional, Enterprise
- **Self-Service Portal**: Customers manage their subscription
- **Usage Tracking**: Token-based billing
- **Webhook Integration**: Real-time subscription updates

## Directory Structure

```
saas/
├── prisma/
│   └── schema.prisma        # Database schema (multi-tenant)
├── backend/
│   ├── __init__.py
│   ├── app.py               # FastAPI application
│   ├── auth.py              # Firebase Auth integration
│   ├── database.py          # Prisma database layer
│   ├── rate_limit.py        # Rate limiting middleware
│   ├── billing.py           # Stripe integration
│   └── routers/
│       ├── webhooks.py      # Webhook API
│       └── integrations.py  # Integration API
├── frontend/
│   ├── src/
│   │   ├── lib/
│   │   │   ├── firebase.ts  # Firebase client
│   │   │   └── api.ts       # API client
│   │   └── ...
│   ├── package.json
│   └── ...
├── deploy/
│   ├── Dockerfile           # Cloud Run container
│   └── cloudbuild.yaml      # CI/CD pipeline
├── firebase.json            # Firebase configuration
└── README.md                # This file
```

## Database Schema

### Core Tables

| Table | Description |
|-------|-------------|
| `Tenant` | Organization/account with subscription |
| `User` | Authenticated user synced from Firebase |
| `Agent` | Tenant-scoped agent instance |
| `Chat` | Conversation thread |
| `Message` | Individual message in chat |
| `Job` | Scheduled/cron job |
| `ApiKey` | Programmatic access key |
| `AuditLog` | Security audit trail |
| `UsageRecord` | Token usage for billing |

### Tenant Isolation

All data tables include `tenantId` column:

```sql
SELECT * FROM agents WHERE "tenantId" = 'tenant_abc123';
```

Queries are automatically scoped through `TenantQuery` helper:

```python
query = TenantQuery(ctx.tenant_id)
agents = await query.find_many(db.agent)
```

## Quick Start

```bash
# 1. Navigate to saas directory
cd saas

# 2. Copy environment file
cp .env.example .env

# 3. Start development environment
docker-compose up -d

# 4. Run database migrations
docker-compose exec backend npx prisma migrate dev

# 5. Access the application
# Frontend: http://localhost:5173
# Backend:  http://localhost:8088
# API Docs: http://localhost:8088/docs (debug mode)
```

## Deployment

### Prerequisites

1. **Google Cloud Project** with billing enabled
2. **Firebase Project** (can be same as GCP project)
3. **Stripe Account** for billing
4. **gcloud CLI** installed and configured
5. **Firebase CLI** installed

### Deploy to Cloud Run

```bash
# Build and deploy
gcloud builds submit \
  --config=saas/deploy/cloudbuild.yaml \
  --substitutions=_REGION=us-central1,_SERVICE_NAME=taskbolt-saas \
  --project=<your-project-id>
```

## Security Checklist

- [x] **Authentication**: Firebase Auth with JWT verification
- [x] **Authorization**: Role-based access control (RBAC)
- [x] **Tenant Isolation**: All queries scoped by tenant_id
- [x] **Rate Limiting**: Per-tenant request quotas
- [x] **API Keys**: Hashed storage, prefix-only display
- [x] **Audit Logging**: All sensitive actions logged
- [x] **Secrets Management**: GCP Secret Manager
- [x] **CORS**: Configurable allowed origins
- [x] **HTTPS**: Enforced by Cloud Run
- [x] **Input Validation**: Pydantic models

## Pricing Plans (Stripe)

| Plan | Price | Agents | Users | Storage |
|------|-------|--------|-------|---------|
| Free | $0 | 1 | 1 | 1GB |
| Starter | $19/mo | 3 | 5 | 10GB |
| Professional | $49/mo | 10 | 25 | 100GB |
| Enterprise | $199/mo | Unlimited | Unlimited | 1TB |

## Support

For issues or questions:
- GitHub Issues: [github.com/taskbolt/Taskbolt](https://github.com/taskbolt/Taskbolt)

## License

See LICENSE file in the root directory.
