# Use a slim Python image for a smaller footprint
FROM python:3.11-slim-bookworm

# Set the working directory inside the container
WORKDIR /app

# Copy the entire application code into the container
COPY . /app

# Expose the port the web UI will listen on
EXPOSE 8083

# Command to run the web UI
# The AGENTS.md mentions `access-list-web.py` as the entrypoint for the web UI.
# Assuming it runs directly with python.
CMD ["python", "access-list-web.py", "--port", "8083", "--addr", "0.0.0.0"]
