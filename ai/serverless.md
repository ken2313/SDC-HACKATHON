# RunPod Serverless (instead of a Pod)

Why: a Pod costs money every hour it is switched on. A **Serverless endpoint** starts a GPU
worker only when the website sends a request and stops it again when idle, so you pay
only for the seconds it works. Good for judging that runs over several days.

Trade-off: when no worker is awake, the **first** request waits while one starts
(a "cold start", often tens of seconds). The website does the AI check in the background
after the stock change, so nobody waits on the page; the flag just appears a bit later.

Nothing else changes: same model, same `server.py`, same website pages.
The Pod setup (`start_server.sh`) still works too.

## What was added
| File | Why |
|---|---|
| `ai/Dockerfile` | Packages the model and `server.py` into a container RunPod can run |
| `ai/.dockerignore` | Keeps training data and scripts out of the container |
| `ai/server.py` | `/ping` health check (RunPod needs it) and `python server.py` start on `$PORT` |
| `backend/app/integrations/ai_client.py` | Sends `Authorization: Bearer <RUNPOD_API_KEY>` when that setting exists |

## Setup (once)
1. **Build the container image** from the `ai/` folder and push it to Docker Hub
   (needs Docker Desktop):
   ```
   cd ai
   docker build --platform linux/amd64 -t YOUR_DOCKERHUB_NAME/siso-anomaly:v1 .
   docker push YOUR_DOCKERHUB_NAME/siso-anomaly:v1
   ```
   (If RunPod offers building from the GitHub repo for this endpoint type, use
   Dockerfile path `ai/Dockerfile` and build context `ai` instead of Docker Hub.)
2. RunPod console -> **Serverless** -> **New Endpoint** -> **Import from Docker Registry**
   -> image `YOUR_DOCKERHUB_NAME/siso-anomaly:v1`.
3. **Endpoint Type: Load Balancer.** Pick a small GPU (16 GB is plenty).
4. **Workers:** Active (always-on) workers = **0** (scale to zero, cheapest).
   Max workers = 1 or 2.
5. **Environment variables:** `INFERENCE_TOKEN` = a long random secret.
6. **Deploy.** Note the **Endpoint ID**. The URL is `https://<endpoint-id>.api.runpod.ai`.
7. RunPod -> **Settings -> API Keys**: create a key (restricted to this endpoint if offered).

## Test it (any terminal with curl)
```
curl -H "Authorization: Bearer <RUNPOD_API_KEY>" https://<endpoint-id>.api.runpod.ai/health
```
The first call may answer "no workers available" while a worker starts; wait ~30 s and retry.
It must show `"device": "cuda"`.

## Replit Secrets (then republish)
| Key | Value |
|---|---|
| `AI_BASE_URL` | `https://<endpoint-id>.api.runpod.ai` |
| `INFERENCE_TOKEN` | the same value as on the endpoint |
| `RUNPOD_API_KEY` | the API key from step 7 |
| `AI_TIMEOUT_S` | `90` (gives a sleeping worker time to start) |

## Demo day
- Send one test request (remove 40 milk) about 5 minutes before judges look, so a worker is warm.
- For a live presentation you may set Active workers = 1 for that hour (billed while on),
  then back to 0.
- Troubleshooting: "PORT_HEALTH" must not be the same port as "PORT" if you set it;
  leaving both at RunPod's defaults works with this container.
