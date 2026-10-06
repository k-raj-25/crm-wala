# Builds either Next app from the monorepo root:  docker build -f deploy/node.Dockerfile --build-arg APP=web .
FROM node:22-slim AS build
ARG APP=web
WORKDIR /repo
COPY package.json package-lock.json ./
COPY packages ./packages
COPY apps ./apps
RUN npm ci
# API_URL is baked into the rewrite table at build time.
ARG API_URL=http://api:5000
ENV API_URL=$API_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build -w @crm/$APP

FROM node:22-slim
ARG APP=web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 APP=$APP
WORKDIR /repo
COPY --from=build /repo /repo
RUN useradd --create-home --uid 10001 app && chown -R app:app /repo/apps/$APP/.next
USER app
CMD ["sh", "-c", "npm run start -w @crm/$APP"]
