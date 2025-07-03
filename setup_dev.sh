#!/bin/bash
# Django Quiz Game - Development Setup Script

echo "🎯 Setting up Django Quiz Game development environment..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "📚 Installing requirements..."
pip install -r requirements.txt

# Check Django configuration
echo "✅ Checking Django configuration..."
python manage.py check

# Run migrations (in case they're needed)
echo "🗄️  Running migrations..."
python manage.py migrate --run-syncdb

echo "🎉 Setup complete! You can now run:"
echo "   source venv/bin/activate"
echo "   python run_daphne.py   # For full WebSocket support"
echo "   # OR"
echo "   python manage.py runserver   # For HTTP-only testing"