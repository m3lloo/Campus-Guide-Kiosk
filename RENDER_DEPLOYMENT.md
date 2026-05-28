# Render Deployment Guide

Complete step-by-step guide to deploy Campus Guide Kiosk on Render.

## Why Render?

✅ **Python-optimized** - Built for Flask apps  
✅ **No cold starts** - Always-on service  
✅ **Free tier available** - $7/month or free with limitations  
✅ **Easy GitHub integration** - Auto-deploy on push  
✅ **Built-in monitoring** - Logs, analytics, health checks  
✅ **Perfect for ML apps** - Persistent memory for embeddings  

---

## Prerequisites

1. ✅ GitHub repository created and pushed (see GITHUB_SETUP.md)
2. ✅ Git remote configured
3. ✅ `Procfile` created (included in this repo)
4. ✅ `requirements.txt` ready (already included)

---

## Deployment Steps

### Step 1: Create Render Account

1. Go to [render.com](https://render.com)
2. Click **Sign Up**
3. Choose **Sign up with GitHub** (easiest)
4. Authorize Render to access your GitHub account

### Step 2: Connect GitHub Repository

1. In Render dashboard, click **New +**
2. Select **Web Service**
3. Click **Connect** under "Connect a repository"
4. Search for `CampusGuideKiosk`
5. Click **Connect** next to your repository

### Step 3: Configure Service

Fill in the deployment form:

| Field | Value |
|-------|-------|
| **Name** | `campus-guide-kiosk` |
| **Environment** | `Python 3` |
| **Region** | `Oregon` (or closest to you) |
| **Branch** | `main` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn --workers 4 --bind 0.0.0.0:$PORT app:app` |
| **Plan** | `Free` or `Starter` ($7/month) |

**Important**: 
- ✅ Select **Free** plan to start
- ✅ Uncheck "Auto-deploy" for now (you'll enable it after setup)

### Step 4: Set Environment Variables

Before deploying, click **Advanced** and add environment variables:

1. Click **Add Environment Variable** for each:

```
FIREBASE_API_KEY         → [Your Firebase API Key]
FIREBASE_PROJECT_ID      → [Your Firebase Project ID]
FIREBASE_APP_ID          → [Your Firebase App ID]
API_KEY_1                → [Your Gemini API Key]
API_KEY_2                → [Your second Gemini key (optional)]
FLASK_ENV                → production
```

**How to find your values:**
- See your `.env` file locally
- DO NOT copy/paste the actual file - enter values one by one

### Step 5: Add Firebase Credentials File

Your `firebase/campus_guide_kiosk.json` is in `.gitignore`, so it won't deploy automatically.

**Option A: Mount via Render** (Recommended)
1. In Render dashboard: **Settings** → **Environment**
2. Scroll to **Disk** section
3. Create a new disk or use existing one
4. Upload `campus_guide_kiosk.json` via dashboard

**Option B: Store as Secret File** (More secure)
1. Encode your JSON file to base64:
   ```bash
   certutil -encode firebase/campus_guide_kiosk.json encoded.txt
   ```
2. Copy the content to a Render environment variable `FIREBASE_CREDENTIALS_B64`
3. Modify `app.py` to decode it on startup

**Option C: Render's Native Secrets** (Easiest)
1. In Render: **Environment** → **Create Env Group**
2. Copy contents of `campus_guide_kiosk.json` → paste into a secret variable
3. Reference in code

---

## Deploy Now!

1. Click **Create Web Service**
2. Render will start building:
   - Installing dependencies
   - Validating Python environment
   - Starting the Flask app

3. Watch the **Logs** tab for output
4. Once deployed, you'll get a URL: `https://campus-guide-kiosk.onrender.com`

---

## Post-Deployment

### ✅ Test Your Deployment

1. Visit `https://campus-guide-kiosk.onrender.com` (should show the kiosk UI)
2. Test the API: `https://campus-guide-kiosk.onrender.com/api/v1/health`
3. Expected response:
```json
{
  "status": "ok",
  "faq_count": 42,
  "model_loaded": true,
  "db_connected": true,
  "api_keys_loaded": 1
}
```

### ❌ Troubleshooting Deployment

#### "Build failed" or "Python not found"
- Check `Procfile` exists and is formatted correctly
- Verify `requirements.txt` has all dependencies
- Check Python version is 3.8+

#### "Import errors" or "Module not found"
- Make sure all packages are in `requirements.txt`
- Check for typos in import statements
- Click **Manual Deploy** to retry build

#### "Firebase connection failed"
- Verify environment variables are set correctly
- Check `firebase/campus_guide_kiosk.json` path and permissions
- Test locally: `python app.py`

#### "Embedding model failed to load"
- First boot takes longer (downloading 80MB model)
- Render free tier has slower downloads
- Wait 2-3 minutes for initial startup
- Check logs for download progress

#### App crashes after 30 seconds
- Likely Firebase credentials issue
- Or model download timing out
- Increase Render plan to "Starter" ($7/mo) for faster network

---

## Enable Auto-Deploy from GitHub

Once verified working:

1. Go to Render dashboard for your service
2. Click **Settings**
3. Scroll to **Auto-Deploy**
4. Toggle **On**
5. Choose branch: `main`

Now every `git push origin main` automatically redeploys!

---

## Monitoring & Logs

### View Logs in Real-Time
1. Render dashboard → Your service
2. Click **Logs** tab
3. See live output, errors, requests

### Set Up Notifications
1. Click **Notifications**
2. Add email/Slack for deployment alerts

### Monitor Performance
1. Click **Metrics** tab
2. View CPU, memory, response times
3. Monitor for issues

---

## Update Your Code

### Workflow:
```bash
# 1. Make changes locally
nano app.py    # or edit in VS Code

# 2. Test locally
python app.py

# 3. Commit changes
git add .
git commit -m "Fix: improve search accuracy"

# 4. Push to GitHub
git push origin main

# 5. Render auto-deploys! (if enabled)
# Watch logs at: dashboard.render.com
```

---

## Scaling & Upgrading

### Free Plan Limits
- ⏱️ Goes to sleep after 15 min inactivity
- 📊 Limited resources
- 🔄 Slow cold starts
- ✅ Good for testing

### Starter Plan ($7/month)
- ⏱️ Always running
- 📊 0.5 GB RAM, 0.5 CPU
- 🔄 No sleep/cold starts
- ✅ Recommended for production

### Higher Plans
- Standard ($12/mo): 1 GB RAM
- Pro ($49/mo): 2 GB RAM, auto-scaling

**Recommendation**: Start Free, upgrade to Starter when ready for production.

---

## Custom Domain (Optional)

1. Buy domain from Namecheap, GoDaddy, etc.
2. In Render dashboard: **Settings** → **Custom Domains**
3. Add your domain
4. Update DNS records (Render will show instructions)
5. Wait 24h for DNS propagation

Example: `campus-kiosk.yourdomain.com`

---

## Environment Variables Reference

Here's what each variable does:

```env
# Firebase
FIREBASE_API_KEY              # Web API key for frontend
FIREBASE_PROJECT_ID           # Your Firebase project
FIREBASE_APP_ID               # Firebase app identifier

# Gemini AI
API_KEY_1                      # Primary Gemini API key
API_KEY_2                      # Secondary key (auto-fallback)

# Flask
FLASK_ENV                      # Set to "production"
RELOAD_SECRET                  # For admin reload endpoint (optional)
APP_RELOAD_URL                 # For admin tool integration (optional)
```

---

## Backup & Recovery

### Backup Your Data
Firebase automatically backs up your database, but:

1. **Download FAQ backups** regularly:
   ```bash
   python index.py    # Export FAQs
   ```

2. **Store backups locally** or in Google Drive

### Restore if Needed
1. Render → Manual Deploy
2. Or delete service and redeploy

---

## Cost Analysis

| Plan | Cost | When to Use |
|------|------|-----------|
| **Free** | $0 | Testing, development |
| **Starter** | $7/mo | Production, always-on |
| **Standard** | $12/mo | High traffic (>100 req/min) |
| **Pro** | $49/mo | Very high traffic, large team |

**Firebase**: Free tier covers most use cases (unless you have 100,000+ FAQs)

---

## Troubleshooting Common Issues

### Issue: "Service failed to start"
```
✅ Solution:
1. Check logs for error messages
2. Verify all environment variables are set
3. Test locally: python app.py
4. Check requirements.txt for missing packages
```

### Issue: "404 - Not Found on all endpoints"
```
✅ Solution:
1. Verify Flask is listening on 0.0.0.0:$PORT
2. Procfile is correct (no extra spaces)
3. app.py has proper routes defined
```

### Issue: "Firebase connection failed"
```
✅ Solution:
1. Check FIREBASE_API_KEY is correct
2. Verify firebase/campus_guide_kiosk.json is deployed
3. Check Firebase project is active
4. Ensure Firestore is enabled in Firebase console
```

### Issue: "Timeout loading model"
```
✅ Solution:
1. First startup takes longer (downloading Sentence Transformers)
2. Wait 3-5 minutes
3. Check Network → see download progress in logs
4. Upgrade to Starter plan for faster connection
```

---

## Security Checklist

- ✅ Environment variables set (not hardcoded)
- ✅ `.env` not in repository (in .gitignore)
- ✅ Firebase credentials not exposed
- ✅ API keys rotated periodically
- ✅ HTTPS enabled by default (Render provides SSL)
- ✅ Logs monitored for errors/attacks

---

## Support & Resources

- **Render Docs**: https://render.com/docs
- **Flask Deployment**: https://flask.palletsprojects.com/en/latest/deploying/
- **Firebase Docs**: https://firebase.google.com/docs
- **Gemini API**: https://ai.google.dev/docs

---

## Next Steps

1. ✅ Create Render account
2. ✅ Connect GitHub repository
3. ✅ Set environment variables
4. ✅ Deploy service
5. ✅ Test health endpoint
6. ✅ Enable auto-deploy
7. ✅ Monitor logs
8. ✅ Share your live URL!

**Your app will be live at:**
```
https://campus-guide-kiosk.onrender.com
```

🎉 **Congratulations! Your Campus Guide Kiosk is now live!**
