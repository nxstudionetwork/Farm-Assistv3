#!/bin/bash
echo "========================================"
echo " Farm Assist - Backend Setup & Start"
echo "========================================"
echo

cd "$(dirname "$0")"

echo "[1/4] Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
fi

echo
echo "[2/4] Activating virtual environment..."
source venv/bin/activate

echo
echo "[3/4] Installing dependencies..."
pip install -r requirements.txt -q

echo
echo "[4/4] Starting Farm Assist Backend..."
echo
echo "========================================"
echo " Backend URL:  http://localhost:8000"
echo " API Docs:     http://localhost:8000/docs"
echo " ReDoc:        http://localhost:8000/redoc"
echo " Frontend:     http://localhost:8000/"
echo " LAN Access:   http://192.168.16.56:8000  (same Wi-Fi)"
echo "========================================"
echo

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
