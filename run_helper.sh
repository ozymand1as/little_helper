#!/bin/bash

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Set environment variables for llama.cpp (defaults from README)
export LLAMA_CPP_URL="${LLAMA_CPP_URL:-http://localhost:8080/v1}"
export LLAMA_CPP_API_KEY="${LLAMA_CPP_API_KEY:-sk-no-key-required}"

# Source the virtual environment
if [ -f "$DIR/venv/bin/activate" ]; then
    source "$DIR/venv/bin/activate"
else
    echo "Error: Virtual environment not found at $DIR/venv"
    exit 1
fi

# Run the application
python "$DIR/main.py"