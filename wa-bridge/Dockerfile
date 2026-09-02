FROM node:20-alpine

WORKDIR /app

ENV NODE_ENV=production \
    WA_BRIDGE_PORT=3200

# Install runtime dependencies
RUN apk add --no-cache ca-certificates

COPY package.json package-lock.json* ./
RUN npm ci --omit=dev

COPY . .

# Create directory for persisted Baileys auth sessions
RUN mkdir -p auth && chown -R node:node /app

USER node

EXPOSE 3200

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD nc -z localhost 3200 || exit 1

CMD ["node", "index.js"]
