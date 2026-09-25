# Admin UI: build the React/Vite/TS SPA, serve the static assets via nginx.
# VITE_API_BASE selects where the SPA calls the API. Default /api: the nginx
# below proxies /api same-origin, which is what lets the refresh token be an
# httpOnly cookie. Override only for a split-origin deployment.
FROM node:20-alpine AS build
WORKDIR /app
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=$VITE_API_BASE
COPY admin-ui/app/package.json ./
RUN npm install
COPY admin-ui/app/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY admin-ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
