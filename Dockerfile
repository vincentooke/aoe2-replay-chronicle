FROM python:3.11-slim

WORKDIR /app

# Final product uses pure standard library (no external pip dependencies)
COPY . /app

ENV PORT=8000
ENV HOST=0.0.0.0

EXPOSE 8000

CMD ["python3", "app/server.py"]
