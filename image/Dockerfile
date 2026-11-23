# Test image for sandbox-run and merge-sweep: Python 3.12, git, spirv-tools and the target repository's test
# packages (image/requirements.txt). Build it once with network; containers from it run with --network none.
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends git spirv-tools \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
