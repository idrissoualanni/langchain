# Start the server in the background
export PYTHONPATH=$(pwd)/backend
export APP_ENV=development
# Use a mock auth or similar if possible, but let's see if it starts.
uvicorn app.main:app --host 127.0.0.1 --port 8000 & 
SERVER_PID=$!

# Wait for it to start
sleep 5

# Try to call the endpoints
echo "Testing /api/user/memory/learning-map..."
curl -v http://127.0.0.1:8000/api/user/memory/learning-map

# Stop the server
kill $SERVER_PID
