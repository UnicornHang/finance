# 前端 Dockerfile - 开发模式
FROM node:20-alpine

WORKDIR /app

# 依赖先行（缓存优化）
COPY package.json ./
RUN npm install

# 应用代码
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]