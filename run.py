import uvicorn
import os
import sys

sys.path.append(os.path.dirname(__file__))

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=True)