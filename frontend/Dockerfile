# syntax=docker/dockerfile:1

ARG NODE_BASE_IMAGE=node:24-alpine
ARG NGINX_BASE_IMAGE=nginx:1.27-alpine

# ---------- Development ----------
FROM ${NODE_BASE_IMAGE} AS dev
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ---------- Build ----------
FROM ${NODE_BASE_IMAGE} AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_SITE_URL=https://mowadhabah.com
ARG VITE_SEARCH_INDEXING=true
ARG VITE_GOOGLE_SITE_VERIFICATION
ARG VITE_BING_SITE_VERIFICATION
RUN npm run build

# ---------- Production (static via nginx, /api proxied to backend) ----------
FROM ${NGINX_BASE_IMAGE} AS prod
ENV PORT=80 \
    BACKEND_HOSTPORT=backend:8000 \
    PUBLIC_SCHEME=http \
    API_MAX_INFLIGHT=128 \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
COPY infra-nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist/.nginx/security-headers.conf /etc/nginx/snippets/xmansx-security-headers.conf
COPY --from=build /app/dist/.nginx/seo-locations.conf /etc/nginx/snippets/xmansx-seo-locations.conf
COPY --from=build /app/dist/.nginx/indexing.conf /etc/nginx/snippets/xmansx-indexing.conf
COPY --chmod=755 infra-render-dns.envsh /docker-entrypoint.d/15-render-dns.envsh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80 10000
