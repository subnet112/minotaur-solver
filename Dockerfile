FROM ghcr.io/subnet112/solver-base:v1

COPY requirements.txt /app/solver/requirements.txt
RUN pip install --no-cache-dir -r /app/solver/requirements.txt

COPY . /app/solver/
WORKDIR /app/solver
