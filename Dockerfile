# Glama/MCP check image: start the server, answer introspection.
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir ".[mcp]"
CMD ["sb-mcp"]
