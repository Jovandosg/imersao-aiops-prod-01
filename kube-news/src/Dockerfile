FROM node:24-alpine

RUN apk add --no-cache tini

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev

COPY . .

USER node

EXPOSE 8080

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["node", "server.js"]
