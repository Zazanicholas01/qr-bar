FROM node:18-bullseye AS base
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install

FROM base AS dev
ENV HOST=0.0.0.0
ENV CHOKIDAR_USEPOLLING=true
COPY . .
EXPOSE 3000
CMD ["npm", "start"]

FROM base AS build
COPY . .
RUN chmod +x node_modules/.bin/react-scripts
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
