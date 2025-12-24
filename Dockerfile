# Dockerfile

# 1. Use an official Python runtime as a parent image
FROM python:3.11-slim

# 2. Set the working directory in the container
WORKDIR /app

# 3. Copy the requirements file into the container at /app
COPY ./requirements.txt /app/requirements.txt

# 4. Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

# 5. Copy the rest of the application's code into the container at /app
COPY . /app

# 6. Expose port 8000 to allow communication to the Uvicorn server
EXPOSE 8000

# 7. Define the command to run the application
# This command will be executed when the container starts.
# It runs the Alembic upgrade to apply migrations and then starts the Uvicorn server.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]