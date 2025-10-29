# Use a slim Python image for a smaller footprint
FROM python:3.11-slim-bookworm

# Set the working directory inside the container
WORKDIR /app

# Copy the entire application code into the container
COPY . /app

# Ensure basic build tools and curl for installer scripts
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright (for headless tests) and fetch Chromium
RUN pip install playwright && playwright install --with-deps chromium

# Optional: install the MCP server adapter for Playwright automation

# Expose the port the web UI will listen on
EXPOSE 8083

# Command to run the web UI
# The docs/AGENTS.md mentions `access-list-web.py` as the entrypoint for the web UI.
# Assuming it runs directly with python.
CMD ["python", "access-list-web.py", "--port", "8083", "--addr", "0.0.0.0"]
