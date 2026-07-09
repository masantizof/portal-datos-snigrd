FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY db.sqlite metadata.json ./

EXPOSE 7860

# Render inyecta el puerto real por la variable $PORT (no siempre 7860); HF
# Spaces usa 7860 fijo. Forma shell (no exec-array) para que se expanda la
# variable de entorno; ${PORT:-7860} cae a 7860 si no está definida.
CMD datasette serve db.sqlite \
    --host 0.0.0.0 --port ${PORT:-7860} \
    --metadata metadata.json \
    --setting sql_time_limit_ms 5000 \
    --setting max_returned_rows 5000 \
    --cors
