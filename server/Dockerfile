FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
RUN useradd --uid 10001 --create-home gallery && mkdir /data && chown gallery /data
USER gallery
ENV GALLERY_DATA=/data
EXPOSE 8787
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8787", "--workers", "1", "--no-access-log"]
