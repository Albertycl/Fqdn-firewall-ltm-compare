# Build stage
FROM node:18-alpine as build-stage

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the app
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built files to nginx html directory
COPY --from=build-stage /app/dist/spa /usr/share/nginx/html

# Copy nginx configuration as a template. The nginx:alpine entrypoint runs
# envsubst over /etc/nginx/templates/*.template at start-up, so BACKEND_URL is
# resolved per deployment instead of being baked into the image.
COPY nginx.conf.template /etc/nginx/templates/nginx.conf.template
ENV NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx
ENV BACKEND_URL=http://127.0.0.1:5432

# Expose port 80
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]