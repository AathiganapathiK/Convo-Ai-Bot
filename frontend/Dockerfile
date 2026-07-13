# ==========================================
# STAGE 1: Build React Application
# ==========================================
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package management files
COPY package.json package-lock.json ./

# Install dependencies using clean install (ci) for reproducibility
RUN npm ci

# Copy frontend source code
COPY . .

# Set build arguments and write them to environment (React bakes them at build time)
ARG REACT_APP_API_BASE_URL=/api
ENV REACT_APP_API_BASE_URL=$REACT_APP_API_BASE_URL

ARG REACT_APP_AUTH0_DOMAIN=dev-num8w577y12rzuuk.us.auth0.com
ENV REACT_APP_AUTH0_DOMAIN=$REACT_APP_AUTH0_DOMAIN

ARG REACT_APP_AUTH0_CLIENT_ID=JEmvncTNoYryytEHrsPUmdXtzaEn0toL
ENV REACT_APP_AUTH0_CLIENT_ID=$REACT_APP_AUTH0_CLIENT_ID

ARG REACT_APP_AUTH0_AUDIENCE=https://rr-convo-ai-api
ENV REACT_APP_AUTH0_AUDIENCE=$REACT_APP_AUTH0_AUDIENCE

# Build production bundle
RUN npm run build

# ==========================================
# STAGE 2: Serve using Nginx
# ==========================================
FROM nginx:1.25-alpine AS runner

# Remove default server configuration
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom optimized Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy production assets from builder stage
COPY --from=builder /app/build /usr/share/nginx/html

# Expose web server port
EXPOSE 80

# Use wget for Alpine-friendly lightweight health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
