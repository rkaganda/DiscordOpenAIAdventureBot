# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /dnd_adventure

# Add metadata to your image for the maintainer
LABEL maintainer="rkaganda@gmail.com"

# Copy the current directory contents into the container at /app
ADD . /dnd_adventure

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Run app.py when the container launches
CMD ["python", "bot.py"]