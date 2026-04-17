# ── Base ───────────────────────────────────────────────
FROM node:20-alpine AS base
WORKDIR /app
COPY package*.json ./
RUN npm install

# ── Development ───────────────────────────────────────
FROM base AS dev
COPY . .
EXPOSE 3000
# Ensure no stale build artifacts are served by Vite
CMD ["sh", "-c", "rm -rf dist && npm run dev -- --host 0.0.0.0"]

# ── Production Build ──────────────────────────────────
FROM base AS builder
COPY . .
RUN npm run build

# ── Runtime ──────────────────────────────────────────
FROM nginx:stable-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
