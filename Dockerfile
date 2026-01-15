FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r /build/requirements.txt

FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY --from=builder /install /usr/local
COPY . /app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
