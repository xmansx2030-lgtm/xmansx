# syntax=docker/dockerfile:1

# ---------- Development ----------
FROM node:24-alpine AS dev
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ---------- Build ----------
FROM node:24-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---------- Production (static via nginx, /api proxied to backend) ----------
FROM nginx:1.27-alpine AS prod
ENV PORT=80 \
    BACKEND_HOSTPORT=backend:8000 \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
COPY infra-nginx.conf /etc/nginx/templates/default.conf.template
COPY infra-security-headers.conf /etc/nginx/snippets/xmansx-security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
