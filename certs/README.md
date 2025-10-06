# TLS Certificates

Place your TLS certificate and key in this directory before starting the reverse proxy. The default Nginx configuration expects the following filenames:

- `fullchain.pem` – full certificate chain for your domain
- `privkey.pem` – corresponding private key

For production use a certificate issued by a trusted CA (e.g. via Let’s Encrypt using certbot or an automated ACME client). You can generate a temporary self-signed certificate for testing:

```bash
openssl req -x509 -nodes -days 7 -newkey rsa:2048 \
  -keyout privkey.pem \
  -out fullchain.pem \
  -subj "/CN=localhost"
```

After placing the files on disk, restart the stack:

```bash
docker compose up -d reverse-proxy
```

If you are running in production, remove or close the plain HTTP port mappings for the backend and frontend services in `docker-compose.yml`.
