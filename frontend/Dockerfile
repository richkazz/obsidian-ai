# =========================
# Build stage
# =========================
FROM node:20-alpine AS builder

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

RUN npm run build


# =========================
# Production stage
# =========================
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# 1. Copies the workspace-mirrored standalone output (this drops the 'app' folder into /app)
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone/ ./

# 2. Copy static assets INSIDE the nested app folder where server.js expects them
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./app/.next/static

# 3. Copy public assets INSIDE the nested app folder
COPY --from=builder --chown=nextjs:nodejs /app/public ./app/public

USER nextjs

EXPOSE 3000

# Start the server from the nested directory
CMD ["node", "app/server.js"]