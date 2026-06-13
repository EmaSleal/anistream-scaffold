# syntax=docker/dockerfile:1
FROM node:20-alpine AS base
WORKDIR /app

# ---- deps: install with frozen lockfile ----
FROM base AS deps
COPY package.json package-lock.json ./
RUN npm ci

# ---- builder: build standalone output ----
FROM base AS builder
ARG APP_URL=http://localhost:3000
ENV APP_URL=$APP_URL
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ---- runner: minimal standalone runtime ----
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
