FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastmcp==3.4.2

COPY server.py .
COPY rubric.py .

EXPOSE 8080

ENV PORT=8080

CMD ["python", "server.py"]
