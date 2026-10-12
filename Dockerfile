FROM python:3.13-slim
WORKDIR /app
COPY server.py config.json proto_send.json proto_recv.json ./
ENV PORT=8080 WS_PORT=29601 WS_PUBLIC_PORT=29601 DATA_DIR=/data PUBLIC_SCHEME=https
VOLUME /data
EXPOSE 8080 29601
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/status',timeout=4)"
CMD ["python", "server.py"]
