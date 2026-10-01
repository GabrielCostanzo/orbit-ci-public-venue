FROM python:3.12-alpine
WORKDIR /app
COPY server.py billing.json build-revision.txt ./
USER 65534:65534
EXPOSE 8080
CMD ["python", "-B", "server.py"]
