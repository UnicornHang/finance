# TLS 证书目录（可选）

将证书放到本目录后重建 / 重启 `nginx` 容器即可启用 HTTPS：

- `fullchain.pem` — 证书链
- `privkey.pem` — 私钥

未放置证书时，生产 Nginx 仅监听 HTTP（80）。

```bash
# 示例：Let's Encrypt 复制
# cp /etc/letsencrypt/live/your.domain/fullchain.pem ./certs/
# cp /etc/letsencrypt/live/your.domain/privkey.pem ./certs/
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --force-recreate nginx
```
