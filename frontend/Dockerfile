FROM node:24.21.0-alpine3.24 AS dependencies

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM dependencies AS development
COPY frontend/ ./
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=10 \
  CMD wget --quiet --spider http://127.0.0.1/ || exit 1
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "80", "--strictPort"]

FROM dependencies AS build
COPY frontend/ ./
RUN npm run build

FROM nginx:1.31.6-alpine3.24

COPY infrastructure/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD wget --quiet --spider http://127.0.0.1/ || exit 1
