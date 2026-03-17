-- ============================================================
--  IDP — Investment Decision Platform
--  Единый скрипт для Supabase SQL Editor
--  Создаёт все таблицы + заполняет справочники
-- ============================================================

-- ============================================================
--  ЧАСТЬ 1: СОЗДАНИЕ ТАБЛИЦ
-- ============================================================

SET timezone = 'Europe/Moscow';

-- 1. Справочник инструментов
CREATE TABLE instrument_dict (
    ticker          VARCHAR(20)  PRIMARY KEY,
    name_ru         VARCHAR(100) NOT NULL,
    asset_class     VARCHAR(20)  NOT NULL
                    CHECK (asset_class IN ('EQUITY','INDEX','BOND','MACRO','COMMODITY')),
    sector          VARCHAR(30),
    source_default  VARCHAR(20)  NOT NULL
                    CHECK (source_default IN ('MOEX','CBR','CBONDS','NSD','BROKER','MANUAL')),
    level           VARCHAR(10)  NOT NULL
                    CHECK (level IN ('L1','L2','L3','BONDS')),
    is_active       BOOLEAN      NOT NULL DEFAULT true,
    valid_min       DECIMAL,
    valid_max       DECIMAL
);

-- 2. Справочник источников данных
CREATE TABLE source_dict (
    source_id       VARCHAR(20)  PRIMARY KEY,
    name_ru         VARCHAR(100) NOT NULL,
    api_url         VARCHAR(200),
    auth_type       VARCHAR(20)  NOT NULL
                    CHECK (auth_type IN ('NONE','API_KEY','SOAP','FILE')),
    rate_limit_ms   INTEGER      DEFAULT 500,
    retry_count     INTEGER      DEFAULT 3
);

-- 3. Журнал ETL-загрузок
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

-- 4. Ручные правки (audit log)
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

-- 5. Версии расчётов (конфигурация)
CREATE TABLE calc_versions (
    version_id      SERIAL       PRIMARY KEY,
    level           VARCHAR(10)  NOT NULL
                    CHECK (level IN ('L1','L2','L3','BONDS')),
    config_json     JSONB        NOT NULL,
    valid_from      DATE         NOT NULL,
    valid_to        DATE,
    created_by      VARCHAR(50)  NOT NULL,
    comment         TEXT
);

CREATE UNIQUE INDEX idx_calc_versions_active
    ON calc_versions (level) WHERE valid_to IS NULL;

-- 6. Контроль качества (лог)
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

-- 7. Сырые рыночные данные (единое хранилище)
CREATE TABLE raw_market_data (
    date            DATE         NOT NULL,
    ticker          VARCHAR(20)  NOT NULL REFERENCES instrument_dict(ticker),
    source          VARCHAR(20)  NOT NULL REFERENCES source_dict(source_id),
    close_price     DECIMAL      NOT NULL,
    volume          BIGINT,
    extra_json      JSONB,
    revision_num    INTEGER      NOT NULL DEFAULT 1,
    etl_run_id      INTEGER      REFERENCES etl_runs(run_id),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (date, ticker, source, revision_num)
);

CREATE INDEX idx_raw_ticker_date ON raw_market_data (ticker, date DESC);
CREATE INDEX idx_raw_etl_run ON raw_market_data (etl_run_id);

-- 8. L1 — Макро-режимы (monthly)
CREATE TABLE l1_regime (
    month           DATE         PRIMARY KEY,
    calc_version_id INTEGER      NOT NULL REFERENCES calc_versions(version_id),
    pmi             DECIMAL,
    cpi_mom         DECIMAL,
    cpi_yoy         DECIMAL,
    ks              DECIMAL,
    imoex           DECIMAL,
    rgbi            DECIMAL,
    bcom            DECIMAL,
    urals           DECIMAL,
    growth_base     DECIMAL,
    monet_base      DECIMAL,
    bcom_score      INTEGER,
    urals_score     INTEGER,
    growth_v5       DECIMAL,
    monet_v5        DECIMAL,
    regime          VARCHAR(20)  NOT NULL,
    risk_cap        VARCHAR(10)  NOT NULL,
    computed_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 9. L2 — Рыночные режимы (daily)
CREATE TABLE l2_daily (
    date                DATE         PRIMARY KEY,
    calc_version_id     INTEGER      NOT NULL REFERENCES calc_versions(version_id),
    vol_score           INTEGER,
    credit_score        INTEGER,
    breadth_score       INTEGER,
    momentum_score      INTEGER,
    liquidity_score     INTEGER,
    correlation_score   INTEGER,
    wms                 DECIMAL,
    regime              VARCHAR(20)  NOT NULL,
    multiplier          DECIMAL      NOT NULL,
    anti_stick_override VARCHAR(50),
    raw_indicators      JSONB,
    computed_at         TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 10. L3 — Скрининг акций (weekly snapshot)
CREATE TABLE l3_screening (
    date            DATE         NOT NULL,
    ticker          VARCHAR(20)  NOT NULL REFERENCES instrument_dict(ticker),
    calc_version_id INTEGER      NOT NULL REFERENCES calc_versions(version_id),
    pe              DECIMAL,
    pbv             DECIMAL,
    ev_ebitda       DECIMAL,
    roe             DECIMAL,
    debt_ratio      DECIMAL,
    dy              DECIMAL,
    price           DECIMAL,
    return_1m       DECIMAL,
    return_3m       DECIMAL,
    return_6m       DECIMAL,
    mom_pctile      DECIMAL,
    rv_pctile       DECIMAL,
    qual_pctile     DECIMAL,
    idea_score      DECIMAL      NOT NULL,
    signal          VARCHAR(10)  NOT NULL
                    CHECK (signal IN ('BUY','HOLD','AVOID')),
    computed_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (date, ticker)
);

CREATE INDEX idx_l3_date ON l3_screening (date DESC);

-- 11. Bonds — Стратегия облигаций (daily)
CREATE TABLE bonds_daily (
    date                DATE         PRIMARY KEY,
    calc_version_id     INTEGER      NOT NULL REFERENCES calc_versions(version_id),
    gbi_ytm             DECIMAL,
    cbi_ytm             DECIMAL,
    g_spread            DECIMAL,
    key_rate            DECIMAL,
    ruonia              DECIMAL,
    cpi_yoy             DECIMAL,
    real_yield          DECIMAL,
    rgbi_index          DECIMAL,
    current_l1_regime   VARCHAR(20)  NOT NULL,
    duration_target     VARCHAR(20),
    credit_segment      VARCHAR(20),
    coupon_type         VARCHAR(20),
    target_ytm          DECIMAL,
    quality_label       VARCHAR(20),
    bond_alloc_pct      INTEGER,
    computed_at         TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ============================================================
--  VIEW: последняя ревизия по каждому тикеру/дате
-- ============================================================

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

-- ============================================================
--  TRIGGER: manual_inputs → raw_market_data
-- ============================================================

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


-- ============================================================
--  ЧАСТЬ 2: ЗАПОЛНЕНИЕ СПРАВОЧНИКОВ
-- ============================================================

-- Источники данных
INSERT INTO source_dict (source_id, name_ru, api_url, auth_type, rate_limit_ms, retry_count) VALUES
    ('MOEX',    'Московская биржа (ISS)',    'https://iss.moex.com/iss',              'NONE',    500, 3),
    ('CBR',     'Центральный банк РФ',       'https://www.cbr.ru/DailyInfoWebServ/',  'SOAP',    1000, 3),
    ('CBONDS',  'Cbonds',                     'https://api.cbonds.info/v2',            'API_KEY', 1000, 3),
    ('NSD',     'НРД',                        NULL,                                    'FILE',    0, 1),
    ('BROKER',  'Брокерский экспорт',         NULL,                                    'FILE',    0, 1),
    ('MANUAL',  'Ручной ввод',                NULL,                                    'NONE',    0, 1);

-- Индексы
INSERT INTO instrument_dict (ticker, name_ru, asset_class, sector, source_default, level, is_active) VALUES
    ('IMOEX',   'Индекс МосБиржи',           'INDEX', NULL, 'MOEX', 'L2', true),
    ('RGBI',    'Индекс гос. облигаций',     'INDEX', NULL, 'MOEX', 'L2', true),
    ('RVI',     'Индекс волатильности',       'INDEX', NULL, 'MOEX', 'L2', true),
    ('MCFTR',   'Индекс полной доходности',   'INDEX', NULL, 'MOEX', 'L2', true);

-- Макро-индикаторы
INSERT INTO instrument_dict (ticker, name_ru, asset_class, sector, source_default, level, is_active, valid_min, valid_max) VALUES
    ('PMI_RU',      'PMI Россия',                 'MACRO', NULL, 'MANUAL',  'L1', true, 30, 70),
    ('CPI_MOM',     'CPI MoM',                    'MACRO', NULL, 'CBR',     'L1', true, -2, 5),
    ('CPI_YOY',     'CPI YoY',                    'MACRO', NULL, 'CBR',     'L1', true, -5, 25),
    ('KEY_RATE',    'Ключевая ставка ЦБ',         'MACRO', NULL, 'CBR',     'L1', true, 0, 30),
    ('RUONIA',      'RUONIA',                      'MACRO', NULL, 'CBR',     'L2', true, 0, 30),
    ('BCOM',        'Bloomberg Commodity Index',   'COMMODITY', NULL, 'MANUAL', 'L1', true, 50, 300),
    ('URALS',       'Urals Oil Price',             'COMMODITY', NULL, 'MANUAL', 'L1', true, 10, 200),
    ('USD_RUB',     'Курс USD/RUB',               'MACRO', NULL, 'CBR',     'L2', true, 30, 200);

-- Bonds-индикаторы
INSERT INTO instrument_dict (ticker, name_ru, asset_class, sector, source_default, level, is_active) VALUES
    ('GBI_YTM',     'Cbonds GBI YTM',             'BOND',  NULL, 'CBONDS', 'BONDS', true),
    ('CBI_YTM',     'Cbonds CBI YTM',             'BOND',  NULL, 'CBONDS', 'BONDS', true);

-- 50 акций
INSERT INTO instrument_dict (ticker, name_ru, asset_class, sector, source_default, level, is_active) VALUES
    ('SBER',    'Сбербанк',              'EQUITY', 'Финансы',               'MOEX', 'L3', true),
    ('SBERP',   'Сбербанк преф',         'EQUITY', 'Финансы',               'MOEX', 'L3', true),
    ('LKOH',    'ЛУКОЙЛ',               'EQUITY', 'Энергетика',            'MOEX', 'L3', true),
    ('GAZP',    'ГАЗПРОМ',              'EQUITY', 'Энергетика',            'MOEX', 'L3', true),
    ('ROSN',    'Роснефть',              'EQUITY', 'Энергетика',            'MOEX', 'L3', true),
    ('NVTK',    'Новатэк',              'EQUITY', 'Энергетика',            'MOEX', 'L3', true),
    ('SIBN',    'Газпрнефть',            'EQUITY', 'Энергетика',            'MOEX', 'L3', true),
    ('TATN',    'Татнефть',              'EQUITY', 'Энергетика',            'MOEX', 'L3', true),
    ('TATNP',   'Татнефть преф',         'EQUITY', 'Энергетика',            'MOEX', 'L3', true),
    ('SNGS',    'Сургутнефтегаз',        'EQUITY', 'Энергетика',            'MOEX', 'L3', true),
    ('SNGSP',   'Сургутнефтегаз преф',   'EQUITY', 'Энергетика',            'MOEX', 'L3', true),
    ('BANE',    'Башнефть',              'EQUITY', 'Энергетика',            'MOEX', 'L3', true),
    ('BANEP',   'Башнефть преф',         'EQUITY', 'Энергетика',            'MOEX', 'L3', true),
    ('TRNFP',   'Транснефть преф',       'EQUITY', 'Энергетика',            'MOEX', 'L3', true),
    ('FLOT',    'Совкомфлот',            'EQUITY', 'Промышленность',        'MOEX', 'L3', true),
    ('VTBR',    'ВТБ',                   'EQUITY', 'Финансы',               'MOEX', 'L3', true),
    ('BSPB',    'БСП',                   'EQUITY', 'Финансы',               'MOEX', 'L3', true),
    ('MOEX',    'МосБиржа',              'EQUITY', 'Финансы',               'MOEX', 'L3', true),
    ('CBOM',    'МКБ',                   'EQUITY', 'Финансы',               'MOEX', 'L3', true),
    ('AFKS',    'АФК Система',           'EQUITY', 'Финансы',               'MOEX', 'L3', true),
    ('LEAS',    'Европлан',              'EQUITY', 'Финансы',               'MOEX', 'L3', true),
    ('GMKN',    'Норникель',             'EQUITY', 'Материалы',             'MOEX', 'L3', true),
    ('NLMK',    'НЛМК',                 'EQUITY', 'Материалы',             'MOEX', 'L3', true),
    ('CHMF',    'Северсталь',            'EQUITY', 'Материалы',             'MOEX', 'L3', true),
    ('MAGN',    'ММК',                   'EQUITY', 'Материалы',             'MOEX', 'L3', true),
    ('RUAL',    'РУСАЛ',                 'EQUITY', 'Материалы',             'MOEX', 'L3', true),
    ('PLZL',    'Полюс',                 'EQUITY', 'Материалы',             'MOEX', 'L3', true),
    ('ALRS',    'АЛРОСА',                'EQUITY', 'Материалы',             'MOEX', 'L3', true),
    ('SELG',    'Селигдар',              'EQUITY', 'Материалы',             'MOEX', 'L3', true),
    ('PHOR',    'ФосАгро',               'EQUITY', 'Материалы',             'MOEX', 'L3', true),
    ('ENPG',    'ЭН+ ГРУП',             'EQUITY', 'Материалы',             'MOEX', 'L3', true),
    ('MTLR',    'Мечел',                 'EQUITY', 'Материалы',             'MOEX', 'L3', true),
    ('MTLRP',   'Мечел преф',            'EQUITY', 'Материалы',             'MOEX', 'L3', true),
    ('SGZH',    'Сегежа Групп',          'EQUITY', 'Материалы',             'MOEX', 'L3', true),
    ('YDEX',    'Яндекс',               'EQUITY', 'ИТ',                    'MOEX', 'L3', true),
    ('POSI',    'Позитив',               'EQUITY', 'ИТ',                    'MOEX', 'L3', true),
    ('VKCO',    'ВК',                    'EQUITY', 'ИТ',                    'MOEX', 'L3', true),
    ('HEAD',    'Хэдхантер',             'EQUITY', 'Промышленность',        'MOEX', 'L3', true),
    ('OZON',    'Озон',                  'EQUITY', 'Потребительские товары', 'MOEX', 'L3', true),
    ('MGNT',    'Магнит',                'EQUITY', 'Потребительские товары', 'MOEX', 'L3', true),
    ('MTSS',    'МТС',                   'EQUITY', 'Услуги связи',          'MOEX', 'L3', true),
    ('RTKM',    'Ростелеком',            'EQUITY', 'Услуги связи',          'MOEX', 'L3', true),
    ('AFLT',    'Аэрофлот',              'EQUITY', 'Промышленность',        'MOEX', 'L3', true),
    ('FEES',    'Россети',               'EQUITY', 'Коммунальные услуги',   'MOEX', 'L3', true),
    ('HYDR',    'РусГидро',              'EQUITY', 'Коммунальные услуги',   'MOEX', 'L3', true),
    ('IRAO',    'Интер РАО',             'EQUITY', 'Коммунальные услуги',   'MOEX', 'L3', true),
    ('UPRO',    'Юнипро',               'EQUITY', 'Коммунальные услуги',   'MOEX', 'L3', true),
    ('MSNG',    'Мосэнерго',             'EQUITY', 'Коммунальные услуги',   'MOEX', 'L3', true),
    ('PIKK',    'ПИК',                   'EQUITY', 'Недвижимость',          'MOEX', 'L3', true),
    ('SMLT',    'Самолет',               'EQUITY', 'Недвижимость',          'MOEX', 'L3', true);

-- Конфигурация L1: Макро-режим
INSERT INTO calc_versions (level, config_json, valid_from, created_by, comment) VALUES
('L1', '{
    "growth_weights": {"pmi": 0.35, "cpi_inv": 0.25, "imoex_ma": 0.20, "rgbi_signal": 0.20},
    "monet_weights":  {"ks_direction": 0.40, "ruonia_spread": 0.30, "inflation_gap": 0.30},
    "commodity_thresholds": {"bcom_6m_change": [-5, 5], "urals_6m_change": [-10, 10]},
    "regime_matrix": {
        "thresholds": {"growth": [-0.3, 0.3], "monet": [-0.3, 0.3]},
        "regimes": [
            ["STAGFLATION",  "STAGNATION", "SLOWDOWN"],
            ["REFLATION",    "TRANSITION", "OVERHEATING"],
            ["RECOVERY",     "GOLDILOCKS", "GROWTH"]
        ],
        "stress_rule": "IF growth_v5 < -0.6 AND monet_v5 < -0.6 THEN STRESS"
    },
    "risk_caps": {
        "GOLDILOCKS": "85%", "GROWTH": "75%", "OVERHEATING": "65%",
        "RECOVERY": "70%", "TRANSITION": "60%", "SLOWDOWN": "55%",
        "REFLATION": "60%", "STAGNATION": "50%", "STAGFLATION": "45%",
        "STRESS": "40%"
    }
}', '2025-01-01', 'system', 'Initial L1 config from Excel model');

-- Конфигурация L2: Рыночный режим
INSERT INTO calc_versions (level, config_json, valid_from, created_by, comment) VALUES
('L2', '{
    "block_weights": {
        "volatility": 1.0,
        "credit": 1.5,
        "liquidity": 1.5,
        "correlation": 0.5,
        "microstructure": 0.5
    },
    "total_weight": 5.0,
    "thresholds": {"risk_on": 7.0, "risk_off": 4.0},
    "multipliers": {"risk_on": 1.2, "neutral": 1.0, "risk_off": 0.5},
    "anti_stick_rules": {"max_consecutive_days": 5, "override_to": "neutral"}
}', '2025-01-01', 'system', 'Initial L2 config from Excel model');

-- Конфигурация L3: Скрининг акций
INSERT INTO calc_versions (level, config_json, valid_from, created_by, comment) VALUES
('L3', '{
    "factor_weights": {"momentum": 0.60, "real_value": 0.25, "quality": 0.15},
    "signal_thresholds": {"buy": 0.620, "avoid": 0.310},
    "momentum_factors": ["6m_return", "3m_return", "1m_return"],
    "value_factors": ["pe_pctile", "pbv_pctile", "ev_ebitda_pctile"],
    "quality_factors": ["roe_pctile", "debt_ratio_inv_pctile", "dy_pctile"]
}', '2025-01-01', 'system', 'Initial L3 config from Excel model');

-- Конфигурация BONDS: Стратегия облигаций
INSERT INTO calc_versions (level, config_json, valid_from, created_by, comment) VALUES
('BONDS', '{
    "strategy_matrix": {
        "GOLDILOCKS":  {"duration": "Long",   "credit": "IG+HY",   "coupon": "Fixed", "quality": "Агрессивно"},
        "GROWTH":      {"duration": "Long",   "credit": "IG+HY",   "coupon": "Fixed", "quality": "Агрессивно"},
        "OVERHEATING": {"duration": "Medium", "credit": "IG",      "coupon": "Float", "quality": "Умеренно"},
        "RECOVERY":    {"duration": "Medium", "credit": "IG+HY",   "coupon": "Fixed", "quality": "Умеренно"},
        "TRANSITION":  {"duration": "Medium", "credit": "IG",      "coupon": "Fixed", "quality": "Умеренно"},
        "SLOWDOWN":    {"duration": "Short",  "credit": "IG",      "coupon": "Float", "quality": "Осторожно"},
        "REFLATION":   {"duration": "Medium", "credit": "IG",      "coupon": "Linker","quality": "Осторожно"},
        "STAGNATION":  {"duration": "Short",  "credit": "IG",      "coupon": "Float", "quality": "Осторожно"},
        "STAGFLATION": {"duration": "Short",  "credit": "IG only", "coupon": "Float", "quality": "Защитно"},
        "STRESS":      {"duration": "Short",  "credit": "IG only", "coupon": "Float", "quality": "Защитно"}
    },
    "alloc_rules": {"base_bond_alloc": 28, "equity_alloc_from_l1": true, "cash_min": 5},
    "yield_targets": {"spread_over_key_rate": -2.0, "min_real_yield": 3.0},
    "quality_thresholds": {
        "aggressive":  ["GOLDILOCKS", "GROWTH"],
        "moderate":    ["RECOVERY", "TRANSITION", "OVERHEATING"],
        "cautious":    ["SLOWDOWN", "REFLATION", "STAGNATION"],
        "defensive":   ["STAGFLATION", "STRESS"]
    }
}', '2025-01-01', 'system', 'Initial Bonds config from Excel model');

-- ============================================================
--  ПРОВЕРКА: должно вернуть 11 таблиц
-- ============================================================
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;
