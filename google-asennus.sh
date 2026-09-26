# ------------------------------------------------------------------
# Googlen asetukset ilman avaintiedostoa. Aja Google Cloud Shellissä.
# Muuta vain kaksi alla olevaa riviä, liitä kaikki Cloud Shelliin ja paina Enter.
# ------------------------------------------------------------------

PROJEKTI="myclub-kalenteri"              # Google Cloud -projektisi ID (Project ID)
GITHUB_REPO="kayttajanimi/myclub-kalenteri"  # GitHub-käyttäjänimesi / repositorion nimi

# --- Tästä alaspäin ei tarvitse muuttaa mitään ---
ROBOTTI="kalenterirobotti@${PROJEKTI}.iam.gserviceaccount.com"
gcloud config set project "$PROJEKTI"

echo ">> Otetaan tarvittavat Googlen palvelut käyttöön..."
gcloud services enable calendar-json.googleapis.com iam.googleapis.com \
  iamcredentials.googleapis.com sts.googleapis.com

echo ">> Luodaan palvelutili (jos sitä ei vielä ole)..."
gcloud iam service-accounts describe "$ROBOTTI" >/dev/null 2>&1 || \
  gcloud iam service-accounts create kalenterirobotti --display-name="Kalenterirobotti"

echo ">> Luodaan GitHub-yhteys..."
gcloud iam workload-identity-pools create github --location=global \
  --display-name="GitHub Actions" 2>/dev/null || echo "   (oli jo olemassa)"
gcloud iam workload-identity-pools providers create-oidc github-repo \
  --location=global --workload-identity-pool=github --display-name="GitHub repo" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository == '${GITHUB_REPO}'" 2>/dev/null || echo "   (oli jo olemassa)"

NUMERO=$(gcloud projects describe "$PROJEKTI" --format='value(projectNumber)')

echo ">> Annetaan GitHub-repositoriolle lupa käyttää palvelutiliä..."
gcloud iam service-accounts add-iam-policy-binding "$ROBOTTI" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${NUMERO}/locations/global/workloadIdentityPools/github/attribute.repository/${GITHUB_REPO}" \
  --format=none

echo ""
echo "=============================================================="
echo " VALMIS! Kopioi nämä GitHubin salaisuuksiksi:"
echo ""
echo " GOOGLE_WIF_PROVIDER:"
echo "   projects/${NUMERO}/locations/global/workloadIdentityPools/github/providers/github-repo"
echo ""
echo " GOOGLE_SERVICE_ACCOUNT:"
echo "   ${ROBOTTI}"
echo ""
echo " Jaa Jääkiekko-kalenteri tälle osoitteelle: ${ROBOTTI}"
echo "=============================================================="
