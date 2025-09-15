FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY src /app/src

RUN pip install --no-cache-dir \
    Flask==3.0.0 \
    gunicorn==21.2.0 \
    qrcode[pil]==7.4.2 \
    Pillow==10.4.0 \
    psycopg[binary]==3.2.1
    \
    stripe==5.4.0

ENV PYTHONPATH=/app/src
ENV PORT=5055
EXPOSE 5055

CMD ["/bin/sh", "-c", "gunicorn -w 2 -k gthread -b 0.0.0.0:${PORT:-5055} checkin_app:app"]
