# Architectural Note & Engineering Trade-offs

## 1. Database Schema & Normalization
The database schema is structured around a central Users table utilizing an enum for roles (admin, provider, customer), which branches directly into Bookings and Reviews. Core identity and authentication data are strictly normalized to prevent credential duplication. 

However, a deliberate normalization trade-off was made on the Bookings table by explicitly embedding both provider_id and customer_id as foreign keys, rather than abstracting them into a generic many-to-many participant mapping table. This slight denormalization optimizes our most frequent read paths, allowing the API to filter a user's schedule with a single indexed query without requiring multi-level relational joins.

## 2. RBAC Architecture & Scalability
Access control relies on a custom FastAPI middleware that intercepts incoming requests, extracts role headers, and binds the identity state to request.state.user. While this flat RBAC approach works effectively for three distinct roles, supporting additional roles (such as an auditor) or multi-tenant organizational hierarchies requires transitioning toward an Attribute-Based Access Control (ABAC) or scope-based permission model.

To support agencies managing multiple providers, the schema would expand to include Organizations and OrganizationMembers tables. Instead of passing static role strings, the middleware would decode JWT payloads containing organization IDs and fine-grained permissions (e.g., org:read:bookings). This allows auditors to securely inspect platform-wide data across agencies without hardcoding rigid, role-specific conditional logic inside router handlers.

## 3. Production Readiness Gaps
While the containerized stack runs seamlessly via Docker Compose, several critical components are required for a production-grade deployment:
- Database Migrations: Schema generation currently relies on SQLAlchemy's Base.metadata.create_all(). In a live environment, Alembic must be integrated to execute version-controlled, non-destructive schema migrations.
- Secrets & Configuration: Environment variables and database credentials currently reside in local setup files. Production deployments must inject secrets dynamically using AWS Secrets Manager or Doppler.
- Authentication Security: Mocked header-based identification (X-User-ID, X-User-Role) must be replaced with cryptographic JWT validation and asymmetric token signing.
- Resilience & Monitoring: Redis worker pools require rate limiting to protect background workers from queue exhaustion, alongside centralized telemetry (via Prometheus or Datadog) to monitor job processing latency.

## 4. Known Edge Cases & Unimplemented Features
- Job Polling Endpoint: The background review summarization task enqueues asynchronously; adding a GET /reviews/jobs/{job_id} polling endpoint would allow clients to track queue execution status in real-time.
- Soft Deletion: Record deletion currently cascades in SQL; implementing soft-delete timestamps (deleted_at) would preserve audit logs for historical bookings and reviews.
