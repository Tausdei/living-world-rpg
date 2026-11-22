FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN useradd --no-create-home --uid 10001 --user-group game \
    && install -d -o game -g game /data
COPY *.py ./
COPY assets ./assets
COPY web ./web
RUN chmod -R a+rX /app
USER game
CMD ["python", "web_game.py"]
