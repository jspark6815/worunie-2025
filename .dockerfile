FROM python:3.12-alpine

WORKDIR /app
RUN apt-get update && apt-get upgrade -y && apt-get clean

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]