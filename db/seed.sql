-- ============================================================
--  IDP — Seed Data
--  Справочники и начальные конфигурации
-- ============================================================

-- ============================================================
--  1. source_dict
-- ============================================================
INSERT INTO source_dict (source_id, name_ru, api_url, auth_type, rate_limit_ms, retry_count) VALUES
    ('MOEX',    'Московская биржа (ISS)',    'https://iss.moex.com/iss',              'NONE',    500, 3),
    ('CBR',     'Центральный банк РФ',       'https://www.cbr.ru/DailyInfoWebServ/',  'SOAP',    1000, 3),
    ('CBONDS',  'Cbonds',                     'https://api.cbonds.info/v2',            'API_KEY', 1000, 3),
    ('NSD',     'НРД',                        NULL,                                    'FILE',    0, 1),
    ('BROKER',  'Брокерский экспорт',         NULL,                                    'FILE',    0, 1),
    ('MANUAL',  'Ручной ввод',                NULL,                                    'NONE',    0, 1);

-- ============================================================
--  2. instrument_dict — Индексы
-- ============================================================
INSERT INTO instrument_dict (ticker, name_ru, asset_class, sector, source_default, level, is_active) VALUES
    ('IMOEX',   'Индекс МосБиржи',           'INDEX', NULL,           'MOEX',   'L2', true),
    ('RGBI',    'Индекс гос. облигаций',     'INDEX', NULL,           'MOEX',   'L2', true),
    ('RVI',     'Индекс волатильности',       'INDEX', NULL,           'MOEX',   'L2', true),
    ('MCFTR',   'Индекс полной доходности',   'INDEX', NULL,           'MOEX',   'L2', true);

-- ============================================================
--  3. instrument_dict — Макро-индикаторы (L1)
-- ============================================================
INSERT INTO instrument_dict (ticker, name_ru, asset_class, sector, source_default, level, is_active, valid_min, valid_max) VALUES
    ('PMI_RU',      'PMI Россия',                 'MACRO', NULL, 'MANUAL',  'L1', true, 30, 70),
    ('CPI_MOM',     'CPI MoM',                    'MACRO', NULL, 'CBR',     'L1', true, -2, 5),
    ('CPI_YOY',     'CPI YoY',                    'MACRO', NULL, 'CBR',     'L1', true, -5, 25),
    ('KEY_RATE',    'Ключевая ставка ЦБ',         'MACRO', NULL, 'CBR',     'L1', true, 0, 30),
    ('RUONIA',      'RUONIA',                      'MACRO', NULL, 'CBR',     'L2', true, 0, 30),
    ('BCOM',        'Bloomberg Commodity Index',   'COMMODITY', NULL, 'MANUAL', 'L1', true, 50, 300),
    ('URALS',       'Urals Oil Price',             'COMMODITY', NULL, 'MANUAL', 'L1', true, 10, 200),
    ('USD_RUB',     'Курс USD/RUB',               'MACRO', NULL, 'CBR',     'L2', true, 30, 200);

-- ============================================================
--  4. instrument_dict — Bonds-индикаторы
-- ============================================================
INSERT INTO instrument_dict (ticker, name_ru, asset_class, sector, source_default, level, is_active) VALUES
    ('GBI_YTM',     'Cbonds GBI YTM',             'BOND',  NULL, 'CBONDS', 'BONDS', true),
    ('CBI_YTM',     'Cbonds CBI YTM',             'BOND',  NULL, 'CBONDS', 'BONDS', true);

-- ============================================================
--  5. instrument_dict — Акции L3 (50 штук)
-- ============================================================
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

-- ============================================================
--  6. calc_versions — Начальные конфигурации
-- ============================================================

-- L1: Макро-режим
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

-- L2: Рыночный режим
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

-- L3: Скрининг акций
INSERT INTO calc_versions (level, config_json, valid_from, created_by, comment) VALUES
('L3', '{
    "factor_weights": {"momentum": 0.60, "real_value": 0.25, "quality": 0.15},
    "signal_thresholds": {"buy": 0.620, "avoid": 0.310},
    "momentum_factors": ["6m_return", "3m_return", "1m_return"],
    "value_factors": ["pe_pctile", "pbv_pctile", "ev_ebitda_pctile"],
    "quality_factors": ["roe_pctile", "debt_ratio_inv_pctile", "dy_pctile"]
}', '2025-01-01', 'system', 'Initial L3 config from Excel model');

-- BONDS: Стратегия облигаций
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
