# Render Deployment - Memory Issue Solutions

## The Problem

Your app crashed with **Out of memory (used over 512MB)** because:

- **Sentence Transformers model**: ~300 MB
- **Embeddings matrix**: ~150 MB
- **Python runtime + Flask**: ~60 MB
- **Total**: ~510 MB (exceeds Render free tier limit of 512 MB)

The free tier on Render is too small for ML models.

---

## Solution: Upgrade to Starter Plan

### Why Starter Plan ($7/month)?

| Feature | Free | Starter |
|---------|------|---------|
| **Memory** | 512 MB | 2 GB ❌ UNLIMITED |
| **vCPU** | Shared | 0.5 |
| **Cost** | $0 | $7/month |
| **Status** | Sleeps after 15min | Always running |
| **Good for** | Testing | Production |

### Upgrade Steps

1. Go to [dashboard.render.com](https://dashboard.render.com)
2. Select **campus-guide-kiosk** service
3. Click **Settings** → **Plan**
4. Choose **Starter** ($7/month)
5. Click **Update Plan**
6. Render will restart your service
7. Watch logs - it should start successfully now!

---

## What Changed Locally

1. **Procfile**: Reduced workers from 3 to **1** (saves ~60 MB per worker)
2. **app.py**: Added memory optimization (OMP_NUM_THREADS)
3. **Timeout increased** to 180s (model loading takes time)

---

## If You Want to Stay on Free Tier (NOT recommended)

### Option 1: Use Lightweight Model
Replace Sentence Transformers with a smaller model:

```python
# Current: ~300 MB
EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")

# Lightweight: ~60 MB
EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
# Or use distilbert-based model
```

**Trade-off**: Slower, less accurate search

### Option 2: Remove Embeddings Cache
Don't keep embeddings in memory:

```python
# Current: Loads all embeddings at startup
# Change to: Load per-query (slower but uses less memory)
```

**Trade-off**: 10x slower responses

### Option 3: Different Platform
- **Railway**: Free with $5 credit/month + 512MB
- **PythonAnywhere**: Free tier + 512MB
- **Google Cloud Run**: Free tier with auto-scaling

---

## Recommendation: Upgrade to Starter

For a production kiosk application:
- ✅ Reliable (always on, not sleeping)
- ✅ Fast responses (enough memory for ML)
- ✅ Only $7/month (cheaper than most platforms)
- ✅ Includes backups, monitoring, logs

**Not recommended**: Keeping free tier for production use

---

## What to Do Now

1. ✅ Commit and push local changes: `git push origin main`
2. ⏳ Go to Render dashboard
3. ⏳ Upgrade to **Starter** plan ($7/month)
4. ⏳ Render will auto-restart your service
5. ✅ Check logs - app should start successfully!

---

## Verify It Works

Once deployed:

```bash
# Test health endpoint
curl https://campus-guide-kiosk.onrender.com/api/v1/health

# Should show:
{
  "status": "ok",
  "faq_count": 42,
  "model_loaded": true,
  "db_connected": true,
  "api_keys_loaded": 1
}
```

---

## Cost Breakdown

| Service | Free | Cost |
|---------|------|------|
| Render (Starter) | N/A | $7/month |
| Firebase | Free tier | $0 (generous limits) |
| Google Gemini | Free tier | $0 (first 2M calls/month) |
| **Total** | - | **$7/month** |

Very affordable for a production kiosk!

---

## Need Help?

- Render docs: https://render.com/docs
- Memory issues: https://render.com/docs/troubleshooting-deploys
- Out of memory: Try upgrading plan or using lightweight model
