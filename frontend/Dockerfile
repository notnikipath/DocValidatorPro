FROM node:20-alpine AS builder
WORKDIR /app
COPY frontend/package.json ./package.json
RUN npm install
COPY frontend .
RUN npm run build

FROM python:3.11-alpine
WORKDIR /srv
COPY --from=builder /app/dist /srv
EXPOSE 5177
CMD ["python", "-m", "http.server", "5177", "--bind", "0.0.0.0", "-d", "/srv"]