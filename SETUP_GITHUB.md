# IDP — Настройка GitHub и автоматического ETL

## 1. Установи GitHub CLI (если ещё нет)
```bash
brew install gh        # macOS
# или: https://cli.github.com/
gh auth login          # авторизуйся через браузер
```

## 2. Инициализируй репо и запуши
```bash
cd ~/путь/к/IDP        # папка проекта

# Инициализация
git init -b main
git add etl/ .github/ db/ .gitignore docker-compose.yml \
        IDP_Dashboard.jsx index.html idp-dashboard.html \
        IDP_Level3_Documentation.md .env.example
git commit -m "IDP: ETL pipeline + DB schema + dashboard

- fetch_moex_daily.py: stocks, indexes, dividends from MOEX ISS
- fetch_cbr_rates.py: KEY_RATE, RUONIA, CPI, USD/RUB from CBR
- fetch_fm_fundamentals.py: PE, PBV, ROE etc from Finance Marker
- GitHub Actions workflow: weekday 19:30 MSK + Monday 08:30 MSK
- PostgreSQL schema (init.sql) + seed data (seed.sql)"

# Создай приватный репо на GitHub и запуши
gh repo create idp-platform --private --source=. --push
```

## 3. Настрой секреты
```bash
gh secret set SUPABASE_URL --body "https://sjrskryuihrirhhrtoqu.supabase.co"
gh secret set SUPABASE_SERVICE_KEY --body "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNqcnNrcnl1aWhyaXJoaHJ0b3F1Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MzczOTAzMiwiZXhwIjoyMDg5MzE1MDMyfQ.WDGfbUgpec2sPeEyUD3XzPe-nRCk6YIShbV3efqQnkY"
gh secret set FM_API_TOKEN --body "52fpg14y1754wsof9b7dfs"
```

## 4. Тестовый запуск
```bash
# Ручной запуск всех ETL-задач
gh workflow run etl.yml --field job=all

# Или по отдельности:
gh workflow run etl.yml --field job=moex
gh workflow run etl.yml --field job=cbr
gh workflow run etl.yml --field job=fm

# Посмотреть статус:
gh run list --workflow=etl.yml
gh run view --log    # последний запуск с логами
```

## 5. Расписание (автоматическое)
- **Пн–Пт 19:30 MSK**: fetch_moex_daily + fetch_cbr_rates
- **Пн 08:30 MSK**: fetch_fm_fundamentals
- Ручной запуск через GitHub Actions UI в любое время
