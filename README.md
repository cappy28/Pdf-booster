# PDF Print-Ready

Analyse et optimise vos PDFs pour l'impression.
**Stack 100% gratuite** — GitHub Pages (frontend) + Render.com (backend).

---

## Déploiement en 3 étapes

### Étape 1 — Pousser sur GitHub

```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/TON_USERNAME/pdf-print-ready.git
git push -u origin main
```

### Étape 2 — Déployer le backend sur Render.com (gratuit)

1. Aller sur https://render.com → créer un compte gratuit
2. New → Web Service → connecter votre repo GitHub
3. Root directory : `backend`
4. Environment : **Docker**
5. Plan : **Free**
6. Cliquer **Deploy**
7. Copier l'URL obtenue (ex: `https://pdf-print-ready-api.onrender.com`)

⚠️ Le free tier de Render "dort" après 15min d'inactivité.
Le premier appel peut prendre 30-60 secondes le temps de démarrer.

### Étape 3 — Activer GitHub Pages (frontend)

1. GitHub → votre repo → Settings → Pages
2. Source : Deploy from branch → main → `/frontend`
3. URL : `https://ton-username.github.io/pdf-print-ready/`
4. Coller l'URL Render dans le champ "API" du site

---

## Ce que fait vraiment le backend

| Fonctionnalité | Technologie | Réel ? |
|---|---|---|
| Analyse DPI | PyMuPDF (pixels réels) | ✅ Oui |
| Conversion A4 | PyMuPDF | ✅ Oui |
| Upscaling 300 DPI | Rasterisation PyMuPDF | ✅ Oui |
| Conversion CMYK | Ghostscript | ✅ Oui |
| Compression | Ghostscript `/printer` | ✅ Oui |
