# Container for RunPod Serverless (endpoint type: Load Balancer).
# It runs the same server.py as the Pod. RunPod starts a GPU worker only when a request
# arrives and stops it again when idle, so you only pay while it is working.
#
# The base image already contains PyTorch with CUDA (GPU support).
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

WORKDIR /app

RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pandas numpy

# Only what inference needs: the trained model, its settings and the server code
COPY config.json scaler.json model.pt model.py features.py server.py ./

# RunPod can override PORT; server.py reads it
ENV PORT=80
EXPOSE 80

CMD ["python", "server.py"]
