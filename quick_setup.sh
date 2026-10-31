#!/bin/bash

echo "=========================================="
echo "RAG_Customer_Service - Quick Setup"
echo "=========================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip -q

# Install requirements
echo ""
echo "Installing requirements..."
echo "This may take a few minutes..."
pip install -r requirements.txt

# Check if .env file exists
echo ""
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "⚠ .env file not found. Creating from .env.example..."
        cp .env.example .env
        echo "✓ .env file created. Please edit it with your API keys."
    else
        echo "⚠ Warning: No .env or .env.example file found"
    fi
else
    echo "✓ .env file exists"
fi

# Run verification
echo ""
echo "Running setup verification..."
python verify_setup.py

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "To activate the virtual environment in the future, run:"
echo "  source venv/bin/activate"
echo ""
echo "To deactivate, run:"
echo "  deactivate"
echo ""
