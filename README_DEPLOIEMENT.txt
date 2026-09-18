╔══════════════════════════════════════════════════════════════╗
║     🍰 DeliStock – Guide de déploiement Vercel + Neon        ║
╚══════════════════════════════════════════════════════════════╝

DURÉE TOTALE : environ 20 minutes
COÛT : 100% GRATUIT

═══════════════════════════════════════════════════════════════
ÉTAPE 1 – Créer la base de données sur Neon (5 min)
═══════════════════════════════════════════════════════════════

1. Allez sur : https://neon.tech
2. Cliquez "Sign Up" → connectez-vous avec Google
3. Cliquez "Create Project"
   - Nom : DeliStock
   - Region : Europe West (Frankfurt)
   - Cliquez "Create Project"
4. Sur la page qui s'affiche, cliquez "Connection string"
5. Copiez la chaîne qui commence par :
   postgresql://...
   ⚠️ GARDEZ-LA, vous en aurez besoin à l'étape 3

═══════════════════════════════════════════════════════════════
ÉTAPE 2 – Créer la clé API Google Vision (5 min)
═══════════════════════════════════════════════════════════════

1. Allez sur : https://console.cloud.google.com
2. Connectez-vous avec votre compte Google
3. Créez un nouveau projet : cliquez sur "Sélectionner un projet"
   → "Nouveau projet" → Nom : DeliStock → Créer
4. Dans le menu gauche : APIs et services → Bibliothèque
5. Cherchez "Cloud Vision API" → cliquez dessus → Activer
6. Menu gauche : APIs et services → Identifiants
7. Cliquez "+ Créer des identifiants" → "Clé API"
8. Copiez la clé affichée (commence par AIza...)
   ⚠️ GARDEZ-LA, vous en aurez besoin à l'étape 3

NOTE : Google offre 1000 analyses d'images/mois GRATUITEMENT
       (sans carte bancaire requise pour ce quota)

═══════════════════════════════════════════════════════════════
ÉTAPE 3 – Déployer sur Vercel (10 min)
═══════════════════════════════════════════════════════════════

1. Allez sur : https://github.com et créez un compte gratuit

2. Créez un nouveau repository :
   - Cliquez "+" → "New repository"
   - Nom : delistock
   - Public ou Private (peu importe)
   - Cliquez "Create repository"

3. Uploadez les fichiers :
   - Cliquez "uploading an existing file"
   - Glissez-déposez TOUT le contenu du dossier
     DeliStock_Vercel (pas le dossier lui-même, son contenu)
   - Cliquez "Commit changes"

4. Allez sur : https://vercel.com
   - Cliquez "Sign Up" → connectez-vous avec GitHub
   - Cliquez "Add New Project"
   - Sélectionnez votre repository "delistock"
   - Cliquez "Import"

5. Dans "Environment Variables", ajoutez ces 2 variables :
   ┌─────────────────────┬─────────────────────────────────┐
   │ DATABASE_URL        │ postgresql://... (copié étape 1)│
   │ GOOGLE_VISION_KEY   │ AIza... (copié étape 2)         │
   └─────────────────────┴─────────────────────────────────┘

6. Cliquez "Deploy" et attendez 2 minutes

7. Vercel vous donne une URL du type :
   https://delistock-xxxx.vercel.app
   → C'est votre DeliStock en ligne ! 🎉

═══════════════════════════════════════════════════════════════
RÉSULTAT FINAL
═══════════════════════════════════════════════════════════════

✅ Accessible partout (PC, téléphone, tablette)
✅ Fonctionne sans PC allumé
✅ Données sauvegardées en permanence sur Neon
✅ Scanner de tickets via Google Vision (1000/mois gratuit)
✅ Installable comme appli Android (PWA)
✅ 100% gratuit

INSTALLER SUR ANDROID :
  1. Ouvrez l'URL Vercel dans Chrome Android
  2. Menu ⋮ → "Ajouter à l'écran d'accueil"
  3. Appuyez "Installer" → icône DeliStock sur votre écran !

