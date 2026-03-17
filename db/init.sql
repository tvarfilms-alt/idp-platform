-- ============================================================
--  IDP — Investment Decision Platform
--  Database Schema v2.1
--  PostgreSQL 15+
-- ============================================================

-- Timezone: все TIMESTAMPTZ хранятся и интерпретируются в MSK
SET timezone = 'Europe/Moscow';

-- ============================================================
--  1. СПРАВОЧНИКИ И СЛУЖЕБНЫЕ ТАБЛИЦЫ
-- ============================================================

-- 1.1 Справочник инструментов
CREATE TABLE instrument_dict (
    ticker          VARCHAR(20)  PRIMARY KEY,
    name_ru         VARCHAR(100) NOT NULL,
    asset_class     VARCHAR(20)  NOT NULL
                    CHECK (asset_class IN ('EQUITY','INDEX','BOND','MACRO','COMMODITY')),
    sector          VARCHAR(30),                          -- для акций: Финансы, Нефтегаз, ...
    source_default  VARCHAR(20)  NOT NULL
                    CHECK (source_default IN ('MOEX','CBR','CBONDS','NSD','BROKER','MANUAL')),
    level           VARCHAR(10)  NOT NULL
                    CHECK (level IN ('L1','L2','L3','BONDS')),
    is_active       BOOLEAN      NOT NULL DEFAULT true,
    valid_min       DECIMAL,                              -- допустимый min для валидации
    valid_max       DECIMAL                               -- допустимый max для валидации
);

COMMENT ON TABLE instrument_dict IS 'Справочник инструментов: тикеры, источники, уровни, диапазоны валидации';

-- 1.2 Справочник источников данных
CREATE TABLE source_dict (
    source_id       VARCHAR(20)  PRIMARY KEY,
    name_ru         VARCHAR(100) NOT NULL,
    api_url         VARCHAR(200),
    auth_type       VARCHAR(20)  NOT NULL
                    CHECK (auth_type IN ('NONE','API_KEY','SOAP','FILE')),
    rate_limit_ms   INTEGER      DEFAULT 500,
    retry_count     INTEGER      DEFAULT 3
);

COMMENT ON TABLE source_dict IS 'Справочник источников данных: API URL, тип авторизации, rate limits';

-- 1.3 Журнал ETL-загрузок
CREATE TABLE etl_runs (
    run_id          SERIAL       PRIMARY KEY,
    source_id       VARCHAR(20)  NOT NULL REFERENCES source_dict(source_id),
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          VARCHAR(20)  NOT NULL DEFAULT 'RUNNING'
                    CHECK (status IN ('RUNNING','SUCCESS','PARTIAL','FAILED')),
    rows_loaded     INTEGER      DEFAULT 0,
    rows_skipped    INTEGER      DEFAULT 0,
    error_message   TEXT,
    backfill        BOOLEAN      NOT NULL DEFAULT false
);

CREATE INDEX idx_etl_runs_source_date ON etl_runs (source_id, started_at DESC);

COMMENT ON TABLE etl_runs IS 'Журнал загрузок: статус каждого ETL-запуска, количество строк, ошибки';

-- 1.4 Ручные правки (audit log)
CREATE TABLE manual_inputs (
    id              SERIAL       PRIMARY KEY,
    date            DATE         NOT NULL,
    ticker          VARCHAR(20)  NOT NULL REFERENCES instrument_dict(ticker),
    value           DECIMAL      NOT NULL,
    entered_by      VARCHAR(50)  NOT NULL,
    entered_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    comment         TEXT,
    is_deleted      BOOLEAN      NOT NULL DEFAULT false
);

CREATE INDEX idx_manual_inputs_ticker_date ON manual_inputs (ticker, date DESC);

COMMENT ON TABLE manual_inputs IS 'Аудит-лог ручных правок. Soft delete, удаление запрещено';

-- 1.5 Версии расчётов (конфигурация)
CREATE TABLE calc_versions (
    version_id      SERIAL       PRIMARY KEY,
    level           VARCHAR(10)  NOT NULL
                    CHECK (level IN ('L1','L2','L3','BONDS')),
    config_json     JSONB        NOT NULL,
    valid_from      DATE         NOT NULL,
    valid_to        DATE,                                 -- NULL = текущая активная версия
    created_by      VARCHAR(50)  NOT NULL,
    comment         TEXT
);

-- Гарантируем: не более одной активной версии на уровень
CREATE UNIQUE INDEX idx_calc_versions_active
    ON calc_versions (level) WHERE valid_to IS NULL;

COMMENT ON TABLE calc_versions IS 'Версионирование конфигов: веса, пороги, формулы. valid_to IS NULL = текущая';

-- 1.6 Контроль качества (лог)
CREATE TABLE data_quality_log (
    id              SERIAL       PRIMARY KEY,
    check_date      DATE         NOT NULL,
    check_type      VARCHAR(30)  NOT NULL
                    CHECK (check_type IN ('MISSING','STALE','OUTLIER','DUPLICATE','RANGE','PARSE')),
    ticker          VARCHAR(20),
    severity        VARCHAR(10)  NOT NULL
                    CHECK (severity IN ('WARN','ERROR','CRITICAL')),
    message         TEXT         NOT NULL,
    resolved        BOOLEAN      NOT NULL DEFAULT false,
    resolved_by     VARCHAR(50)
);

CREATE INDEX idx_dq_log_date ON data_quality_log (check_date DESC);
CREATE INDEX idx_dq_log_unresolved ON data_quality_log (resolved) WHERE resolved = false;

COMMENT ON TABLE data_quality_log IS 'Лог проверок качества данных: пропуски, выбросы, дубли';


-- ============================================================
--  2. ОСНОВНЫЕ ТАБЛИЦЫ ДАННЫХ
-- ============================================================

-- 2.1 Сырые рыночные данные (единое хранилище)
CREATE TABLE raw_market_data (
    date            DATE         NOT NULL,
    ticker          VARCHAR(20)  NOT NULL REFERENCES instrument_dict(ticker),
    source          VARCHAR(20)  NOT NULL REFERENCES source_dict(source_id),
    close_price     DECIMAL      NOT NULL,
    volume          BIGINT,                               -- NULL для макро-индикаторов
    extra_json      JSONB,                                -- OHLC, bid/ask, доп. поля
    revision_num    INTEGER      NOT NULL DEFAULT 1,
    etl_run_id      INTEGER      REFERENCES etl_runs(run_id),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),

    PRIMARY KEY (date, ticker, source, revision_num)
);

-- Быстрый поиск последнего значения по тикеру
CREATE INDEX idx_raw_ticker_date ON raw_market_data (ticker, date DESC);

-- Поиск по ETL-запуску (для rollback / аудита)
CREATE INDEX idx_raw_etl_run ON raw_market_data (etl_run_id);

COMMENT ON TABLE raw_market_data IS 'Сырые данные из всех источников. PK включает revision_num для immutable append';

-- 2.2 L1 — Макро-режимы (monthly)
CREATE TABLE l1_regime (
    month           DATE         PRIMARY KEY,             -- первый день месяца
    calc_version_id INTEGER      NOT NULL REFERENCES calc_versions(version_id),
    -- Сырые индикаторы
    pmi             DECIMAL,
    cpi_mom         DECIMAL,
    cpi_yoy         DECIMAL,
    ks              DECIMAL,                              -- ключевая ставка
    imoex           DECIMAL,
    rgbi            DECIMAL,
    bcom            DECIMAL,
    urals           DECIMAL,
    -- Промежуточные скоры
    growth_base     DECIMAL,
    monet_base      DECIMAL,
    bcom_score      INTEGER,                              -- -1, 0, 1
    urals_score     INTEGER,                              -- -1, 0, 1
    -- Итоговые скоры
    growth_v5       DECIMAL,
    monet_v5        DECIMAL,
    -- Результат
    regime          VARCHAR(20)  NOT NULL,
    risk_cap        VARCHAR(10)  NOT NULL,
    computed_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON TABLE l1_regime IS 'L1 макро-режимы: monthly. Один режим на месяц';

-- 2.3 L2 — Рыночные режимы (daily)
CREATE TABLE l2_daily (
    date                DATE         PRIMARY KEY,
    calc_version_id     INTEGER      NOT NULL REFERENCES calc_versions(version_id),
    -- Блочные скоры (0/1/2)
    vol_score           INTEGER,
    credit_score        INTEGER,
    breadth_score       INTEGER,
    momentum_score      INTEGER,
    liquidity_score     INTEGER,
    correlation_score   INTEGER,
    -- Итог
    wms                 DECIMAL,                          -- взвешенный рыночный скор
    regime              VARCHAR(20)  NOT NULL,             -- Risk-on / Neutral / Risk-off
    multiplier          DECIMAL      NOT NULL,             -- 0.5 / 1.0 / 1.2
    anti_stick_override VARCHAR(50),                       -- применённое правило
    raw_indicators      JSONB,                             -- RVI, RUONIA spread, корреляция и т.д.
    computed_at         TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON TABLE l2_daily IS 'L2 рыночные режимы: daily. Блочные скоры + WMS + режим';

-- 2.4 L3 — Скрининг акций (weekly snapshot)
CREATE TABLE l3_screening (
    date            DATE         NOT NULL,
    ticker          VARCHAR(20)  NOT NULL REFERENCES instrument_dict(ticker),
    calc_version_id INTEGER      NOT NULL REFERENCES calc_versions(version_id),
    -- Фундаментальные метрики
    pe              DECIMAL,
    pbv             DECIMAL,
    ev_ebitda       DECIMAL,
    roe             DECIMAL,
    debt_ratio      DECIMAL,
    dy              DECIMAL,                              -- dividend yield
    -- Ценовые данные
    price           DECIMAL,
    return_1m       DECIMAL,
    return_3m       DECIMAL,
    return_6m       DECIMAL,
    -- Факторные перцентили (0–1)
    mom_pctile      DECIMAL,
    rv_pctile       DECIMAL,
    qual_pctile     DECIMAL,
    -- Итог
    idea_score      DECIMAL      NOT NULL,                -- 0–1
    signal          VARCHAR(10)  NOT NULL
                    CHECK (signal IN ('BUY','HOLD','AVOID')),
    computed_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),

    PRIMARY KEY (date, ticker)
);

CREATE INDEX idx_l3_date ON l3_screening (date DESC);

COMMENT ON TABLE l3_screening IS 'L3 скрининг: weekly. 50 акций × факторы × IdeaScore × сигнал';

-- 2.5 Bonds — Стратегия облигаций (daily)
CREATE TABLE bonds_daily (
    date                DATE         PRIMARY KEY,
    calc_version_id     INTEGER      NOT NULL REFERENCES calc_versions(version_id),
    -- Рыночные данные
    gbi_ytm             DECIMAL,                          -- доходность ГО индекса
    cbi_ytm             DECIMAL,                          -- доходность корп. индекса
    g_spread            DECIMAL,                          -- CBI YTM − GBI YTM
    key_rate            DECIMAL,
    ruonia              DECIMAL,
    cpi_yoy             DECIMAL,
    real_yield           DECIMAL,                          -- GBI YTM − CPI YoY
    rgbi_index          DECIMAL,
    -- Стратегия (из матрицы на базе L1 режима)
    current_l1_regime   VARCHAR(20)  NOT NULL,
    duration_target     VARCHAR(20),                       -- Short / Medium / Long
    credit_segment      VARCHAR(20),                       -- IG / IG+HY / HY
    coupon_type         VARCHAR(20),                       -- Fixed / Float / Linker
    target_ytm          DECIMAL,
    quality_label       VARCHAR(20),                       -- Агрессивно / Умеренно / Осторожно / Защитно
    bond_alloc_pct      INTEGER,                           -- рекомендуемая доля облигаций (%)
    computed_at         TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON TABLE bonds_daily IS 'Bonds: daily. Рыночные метрики + стратегия из L1-матрицы';


-- ============================================================
--  3. ВСПОМОГАТЕЛЬНЫЕ ОБЪЕКТЫ
-- ============================================================

-- View: последняя ревизия по каждому тикеру/дате
CREATE VIEW v_raw_latest AS
SELECT r.*
FROM raw_market_data r
INNER JOIN (
    SELECT date, ticker, source, MAX(revision_num) AS max_rev
    FROM raw_market_data
    GROUP BY date, ticker, source
) latest
ON  r.date = latest.date
AND r.ticker = latest.ticker
AND r.source = latest.source
AND r.revision_num = latest.max_rev;

COMMENT ON VIEW v_raw_latest IS 'Последняя ревизия каждого наблюдения. Compute читает ТОЛЬКО отсюда';

-- Trigger: auto-copy manual_inputs → raw_market_data
CREATE OR REPLACE FUNCTION fn_manual_to_raw()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO raw_market_data (date, ticker, source, close_price, revision_num, created_at)
    VALUES (NEW.date, NEW.ticker, 'MANUAL', NEW.value, 1, now())
    ON CONFLICT (date, ticker, source, revision_num) DO UPDATE
        SET close_price = EXCLUDED.close_price,
            created_at  = EXCLUDED.created_at;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_manual_to_raw
    AFTER INSERT ON manual_inputs
    FOR EACH ROW
    WHEN (NEW.is_deleted = false)
    EXECUTE FUNCTION fn_manual_to_raw();

COMMENT ON FUNCTION fn_manual_to_raw IS 'Канонический путь: manual_inputs → raw_market_data (source=MANUAL)';
