# Dockerfile for the streamlit application

FROM python:3.11

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libreoffice \
    software-properties-common \
    && rm -rf /var/lib/apt/lists/*

# Install the requirements
COPY requirements.txt /app
RUN pip3 install -r requirements.txt

COPY discord_requirements.txt /app
RUN pip3 install -r discord_requirements.txt

# Copy the local files to the image
# This copies everything over after the pip install so that we don't have to
# reinstall the dependencies every time we make a change to the code
COPY . /app

EXPOSE 8500

HEALTHCHECK CMD curl --fail http://localhost:8500/_stcore/health

ENTRYPOINT ["streamlit", "run", "About.py", "--server.port=8500", "--server.address=0.0.0.0", "--server.fileWatcherType=none"]