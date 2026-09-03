FROM node:20-alpine

# Enable corepack for pnpm
RUN corepack enable && corepack prepare pnpm@9.0.0 --activate

WORKDIR /app

# Copy workspace config first for layer caching
COPY pnpm-workspace.yaml ./
COPY packages/shared/package.json ./packages/shared/
COPY apps/web/package.json ./apps/web/

# Install dependencies
RUN pnpm install --no-frozen-lockfile || npm install --prefix apps/web

# Copy source files
COPY packages/shared ./packages/shared
COPY apps/web ./apps/web

EXPOSE 5173

CMD ["npm", "--prefix", "apps/web", "run", "dev"]
