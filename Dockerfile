FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy
WORKDIR /app
RUN pip install --no-cache-dir playwright==1.49.0 requests
COPY . /app
ENV PYTHONUNBUFFERED=1
CMD ["python", "vinted_bot.py"]
