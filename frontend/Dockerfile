# Build stage — standalone CRA build (direct access / standalone mode)
FROM node:18-alpine AS build-standalone
WORKDIR /app
COPY package*.json ./
RUN npm install --legacy-peer-deps
COPY . .
RUN npm run build

# Build stage — MFE build (served as FuzeFront remote via module federation)
FROM node:18-alpine AS build-mfe
WORKDIR /app
COPY package*.json ./
RUN npm install --legacy-peer-deps
COPY . .
RUN npm run build:mfe

# Production stage
FROM nginx:alpine

RUN apk add --no-cache curl

# Standalone app at /
COPY --from=build-standalone /app/build /usr/share/nginx/html

# MFE assets at /apps/fuzekeys/ (FuzeFront fetches remoteEntry.js from here)
COPY --from=build-mfe /app/dist-mfe /usr/share/nginx/html/apps/fuzekeys

COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
