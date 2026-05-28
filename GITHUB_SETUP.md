# GitHub Deployment Guide for Campus Guide Kiosk

## Overview
Your project is now **ready for GitHub**! All sensitive files are excluded, unused large files are removed, and essential documentation is in place.

## Quick Stats
✅ **Freed up space**: 172 MB (removed unused ML models)  
✅ **Files tracked**: 14 production files  
✅ **Repo size**: ~1.5 MB (excluding venv)  
✅ **Status**: Production-ready  

---

## Step 1: Create a GitHub Repository

### Option A: Using GitHub Web UI
1. Go to [github.com/new](https://github.com/new)
2. **Repository name**: `CampusGuideKiosk` (or your preferred name)
3. **Description**: "An interactive AI-powered campus information kiosk with 3D map integration"
4. Choose **Public** or **Private** (based on your needs)
5. **DO NOT** initialize with README, .gitignore, or license (you already have these)
6. Click **Create repository**

### Option B: Using GitHub CLI
```bash
gh repo create CampusGuideKiosk --description "AI-powered campus information kiosk" --public
```

---

## Step 2: Push Your Repository to GitHub

### 1. Add Remote and Push
```bash
cd c:\Users\Mello\source\repos\CampusGuideKiosk\CampusGuideKiosk

# Add the GitHub remote
git remote add origin https://github.com/YOUR_USERNAME/CampusGuideKiosk.git

# Rename branch to main (GitHub standard)
git branch -M main

# Push to GitHub
git push -u origin main
```

### 2. Verify Successful Push
Go to `https://github.com/YOUR_USERNAME/CampusGuideKiosk` and confirm you see:
- ✅ All code files
- ✅ .gitignore, requirements.txt, README.md
- ✅ .env.example (but NOT .env)
- ✅ firebase/.gitkeep (but NOT campus_guide_kiosk.json)
- ✅ No venv, __pycache__, or .vs folders

---

## Step 3: Configure Secrets (GitHub Actions)

If you plan to deploy with GitHub Actions, store sensitive credentials as GitHub secrets:

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Add these secrets:
   - `FIREBASE_API_KEY`
   - `FIREBASE_PROJECT_ID`
   - `FIREBASE_APP_ID`
   - `GEMINI_API_KEY`

Reference them in workflows as `${{ secrets.FIREBASE_API_KEY }}`

---

## Step 4: Optional - Add GitHub Actions for CI/CD

Create `.github/workflows/test.yml` for automated testing:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest
    
    - name: Run tests
      run: pytest tests/
```

---

## Step 5: Clone and Test Locally (Verification)

To verify the repository works correctly, clone it fresh:

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/CampusGuideKiosk.git
cd CampusGuideKiosk

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Copy .env configuration
cp .env.example .env
# Edit .env with your actual credentials

# Run the app
python app.py
```

---

## Important Notes

### Security Best Practices

1. **Never commit secrets**
   - ✅ `.env` is in `.gitignore` (safe)
   - ✅ `firebase/campus_guide_kiosk.json` is in `.gitignore` (safe)
   - ❌ Do NOT remove these from .gitignore

2. **Protect Firebase Credentials**
   - Keep `firebase/campus_guide_kiosk.json` only on your local machine
   - Deploy only using GitHub secrets or environment variables

3. **API Key Rotation**
   - Store API keys as GitHub secrets
   - Rotate keys periodically
   - Use the key rotation feature in `app.py`

### Managing Credentials on New Machines

When cloning on a new machine:

```bash
git clone https://github.com/YOUR_USERNAME/CampusGuideKiosk.git
cd CampusGuideKiosk

# The .env and firebase credentials will be MISSING (expected!)
# You must provide them:

# 1. Copy your .env file from original machine
# 2. Copy your firebase/campus_guide_kiosk.json from original machine

# These files will NOT be tracked by git (as intended)
# Verify: git status should NOT show these files
```

---

## Deployment Options

### ⭐ Option 1: Render (RECOMMENDED)
Best for Flask apps with ML models and persistent memory.

**Features:**
- ✅ Python-optimized
- ✅ $7/month for always-on service
- ✅ Free tier available
- ✅ Auto-deploy from GitHub
- ✅ Built-in monitoring

**Quick Start:**
1. Go to [render.com](https://render.com)
2. Sign up with GitHub
3. Connect `CampusGuideKiosk` repository
4. Set environment variables
5. Deploy!

**Full Guide:** See [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md)

```bash
# Or deploy via CLI:
npm i -g @render/cli
render login
render init
```

---

### Option 2: PythonAnywhere (Good for educational projects)
Simplest option - no CLI needed.

1. Sign up at [pythonanywhere.com](https://www.pythonanywhere.com)
2. Create new web app (Flask)
3. Upload files and set up virtual environment
4. Configure .env in web app settings
5. Set API keys as environment variables

**Cost:** Free tier available, $5+/month for production

---

### Option 3: Heroku (Legacy - Free tier removed)
```bash
# Note: Heroku removed free tier. Now starts at $7/month like Render
# Use Render instead (simpler setup)

heroku login
heroku create your-app-name
echo "web: gunicorn --workers 4 app:app" > Procfile
heroku config:set FIREBASE_API_KEY=your_key
git push heroku main
```

---

### Option 4: Docker + Cloud Run (Google Cloud)
For advanced users wanting serverless + scaling.

See the Dockerfile template in README.md

**Cost:** Pay-per-use, free tier available ($5 credit/month)

---

### Option 5: Your Own Server
Use `gunicorn` with a reverse proxy (nginx) on a VPS.

**Providers:** DigitalOcean, Linode, AWS EC2

**Cost:** $5-20/month depending on server size

---

## Updating Your Repository

### After Making Changes Locally:
```bash
git add .
git commit -m "Description of changes"
git push origin main
```

### Common Workflow:
```bash
# Create a feature branch
git checkout -b feature/new-feature

# Make changes...
git add .
git commit -m "Add new feature"

# Push to GitHub
git push origin feature/new-feature

# Create Pull Request on GitHub (optional)
# After review, merge to main
```

---

## Repository Maintenance

### Add a License
```bash
# Add MIT License
echo "MIT License text here..." > LICENSE
git add LICENSE
git commit -m "Add MIT License"
git push
```

### Add GitHub Topics (for discoverability)
1. Go to your repo **Settings**
2. Scroll to **About** section
3. Add topics: `flask`, `ai`, `campus-guide`, `firebase`, `gemini`

### Enable GitHub Pages (for documentation)
1. Go to **Settings** → **Pages**
2. Set source to `main` branch
3. Choose a theme

---

## Troubleshooting

### "fatal: remote origin already exists"
```bash
git remote remove origin
git remote add origin https://github.com/YOUR_USERNAME/CampusGuideKiosk.git
```

### "Permission denied (publickey)"
Set up SSH keys: https://docs.github.com/en/authentication/connecting-to-github-with-ssh

### ".env accidentally committed"
```bash
# Remove from git history (careful operation!)
git rm --cached .env
git commit -m "Remove .env from tracking"
git push

# For history cleanup:
git filter-branch --tree-filter 'rm -f .env' HEAD
```

### Repository too large
GitHub has a 100 MB file limit. If uploading fails:
- Use Git LFS for large files: `git lfs install`
- Or remove large files and use `.gitkeep` placeholder

---

## Next Steps

1. ✅ Create GitHub repository
2. ✅ Push your code
3. ✅ Test cloning on another machine
4. ✅ Set up GitHub secrets for deployment
5. ✅ Choose deployment platform
6. ✅ Document any campus-specific setup in README
7. ✅ Consider adding GitHub Issues for bug tracking
8. ✅ Add team members as collaborators (if needed)

---

## Need Help?

- **GitHub Docs**: https://docs.github.com
- **Flask Deployment**: https://flask.palletsprojects.com/en/latest/deploying/
- **Firebase Setup**: https://firebase.google.com/docs
- **Gemini API**: https://ai.google.dev/docs

Good luck! Your project is ready for the world! 🚀
