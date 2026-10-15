FROM python:3.14-slim AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels ".[postgres]"

FROM python:3.14-slim
ARG CODE_COMMIT=unknown
ENV VCORE_CODE_COMMIT=${CODE_COMMIT} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 vcore && mkdir -p /data/objects && chown vcore /data/objects
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
USER vcore
EXPOSE 8000
CMD ["uvicorn", "--factory", "verification_core.api:create_app", "--host", "0.0.0.0", "--port", "8000"]
