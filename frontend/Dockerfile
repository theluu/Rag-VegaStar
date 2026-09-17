# Build giao diện rồi phục vụ file tĩnh bằng nginx (user không root)
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL
ARG VITE_MAP_STYLE_URL
ARG VITE_SITE_URL
ARG VITE_API_KEY
ARG VITE_LOGIN_HINT
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_MAP_STYLE_URL=$VITE_MAP_STYLE_URL \
    VITE_SITE_URL=$VITE_SITE_URL \
    VITE_API_KEY=$VITE_API_KEY \
    VITE_LOGIN_HINT=$VITE_LOGIN_HINT
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
# Template được envsubst khi khởi động → CSP khớp địa chỉ API và bản đồ thực tế
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
ENV NGINX_ENVSUBST_FILTER="^(API_ORIGIN|MAP_ORIGIN)$"
EXPOSE 8080
