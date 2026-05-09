FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app
ARG INSTALL_LOCAL_EMBEDDINGS=false

# Copy only requirements first for better caching
# This layer will be cached unless requirements files change
COPY requirements.txt requirements-local-embeddings.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
		&& if [ "$INSTALL_LOCAL_EMBEDDINGS" = "true" ]; then \
				 pip install --no-cache-dir -r requirements-local-embeddings.txt; \
			 fi

# Copy the rest of the application
# This layer will be rebuilt only when code changes
COPY . .

EXPOSE 8000

# Use --reload for development (auto-reload on code changes)
# For production, remove --reload flag
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
