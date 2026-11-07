ARG NGINX_IMAGE=nginx:1.27.4-alpine
FROM ${NGINX_IMAGE}

COPY nginx.conf /etc/nginx/nginx.conf
COPY 40-rutas.sh /docker-entrypoint.d/40-rutas.sh
RUN chmod +x /docker-entrypoint.d/40-rutas.sh
