FROM python:3.11-slim

# Install system deps: opencv headless, potrace (vector tracing), pdflatex
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    potrace \
    texlive-latex-base \
    texlive-latex-extra \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# CV service runs on port 8077 (matches SLIDEGEN_CV_SERVICE_URL default)
EXPOSE 8077

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8077"]
