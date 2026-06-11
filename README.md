# Inveo JIRA Dashboard

Automaticky aktualizovaný dashboard status změn z JIRA.  
Každé pondělí v 7:00 (CZ) se stáhnou data za posledních 90 dní a dashboard se aktualizuje.

## Živý dashboard

Po nastavení bude dostupný na:
```
https://TVOJE-GITHUB-JMENO.github.io/inveo-dashboard/
```

## Prvotní nastavení (jednorázově)

### 1. JIRA API token
1. Jdi na https://id.atlassian.com/manage-profile/security/api-tokens
2. Klikni **Create API token**
3. Pojmenuj ho `GitHub Actions` a zkopíruj token

### 2. GitHub Secrets
V repozitáři jdi na **Settings → Secrets and variables → Actions → New repository secret**:

| Name | Value |
|------|-------|
| `JIRA_EMAIL` | `email@inveo.cz` |
| `JIRA_TOKEN` | token z kroku 1 |

### 3. GitHub Pages
V repozitáři jdi na **Settings → Pages**:
- Source: **Deploy from a branch**
- Branch: **main** / složka **docs**
- Klikni **Save**

### 4. První spuštění
Jdi na **Actions → Aktualizace JIRA dashboardu → Run workflow**.  
Za 5–10 minut bude dashboard živý na URL výše.

## Ruční spuštění
**Actions → Aktualizace JIRA dashboardu → Run workflow** — kdykoliv chceš aktualizovat mimo plánovaný čas.

## Změna rozsahu dat
V `generate_dashboard.py` uprav řádek:
```python
DATE_FROM = DATE_TO - timedelta(days=90)
```
Například `days=180` pro půl roku.
