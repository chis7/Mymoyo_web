# 1. Use a lightweight Python environment
FROM python:3.11-slim

# 2. Optimize Python output for Docker logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Create a generic container folder (Leave this as /app)
WORKDIR /app

# 4. Install your Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy your local project files into the container
COPY . /app/

# 6. Expose the port for web traffic
EXPOSE 8000

# 7. CHANGER HERE: Replace 'my_django_project' with your exact project folder name
CMD ["gunicorn", "--bind", "0.0.0.0:7000", "mymoyo.wsgi"]
