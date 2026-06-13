# JobRadar frontend — build with Vite, serve static bundle via nginx
# Stage 1: build
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# VITE_API_URL is intentionally left empty: the app falls back to relative
# "/api" paths, which nginx proxies to the backend (see nginx.conf). This
# keeps the browser on a single origin and avoids CORS entirely.
RUN npm run build

# Stage 2: serve
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
