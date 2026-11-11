FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.0 /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PYTHON_DOWNLOADS=0 UV_LINK_MODE=copy
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project
COPY . .
RUN DJANGO_SECRET_KEY=build-only-key DATABASE_URL=sqlite:///:memory: DJANGO_ALLOWED_HOSTS=localhost uv run --no-dev python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
