# Admin UI: build the React/Vite/TS SPA, serve the static assets via nginx.
# VITE_API_BASE selects where the SPA calls the API:
#   dev  -> http://localhost:8000 (backend directly; CORS-allowed)
#   prod -> /api  (same-origin, behind the reverse proxy)
FROM node:20-alpine AS build
WORKDIR /app
ARG VITE_API_BASE=http://localhost:8000
ENV VITE_API_BASE=$VITE_API_BASE
COPY admin-ui/app/package.json ./
RUN npm install
COPY admin-ui/app/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY admin-ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
