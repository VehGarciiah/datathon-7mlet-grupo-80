CREATE TABLE contact_channel (
    channel_id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL,
    display_name text NOT NULL,
    CONSTRAINT uq_contact_channel_code UNIQUE (code),
    CONSTRAINT ck_contact_channel_code CHECK (code IN ('celular', 'telefone')),
    CONSTRAINT ck_contact_channel_display_name CHECK (btrim(display_name) <> '')
);

CREATE TABLE contact_opportunity (
    opportunity_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_id text NOT NULL,
    source_event_id bigint NOT NULL,
    month_code text NOT NULL,
    weekday_code text NOT NULL,
    previous_outcome_code text NOT NULL,
    days_since_previous_contact smallint,
    previous_campaign_contacts smallint NOT NULL,
    current_campaign_previous_attempts smallint NOT NULL,
    employment_variation_rate numeric(4, 1) NOT NULL,
    consumer_price_index numeric(6, 3) NOT NULL,
    consumer_confidence_index numeric(5, 1) NOT NULL,
    euribor_3_months numeric(6, 3) NOT NULL,
    employed_count numeric(7, 1) NOT NULL,
    never_contacted_before boolean NOT NULL,
    contact_authorized boolean NOT NULL DEFAULT true,
    do_not_contact boolean NOT NULL DEFAULT false,
    historical_channel_id smallint NOT NULL,
    historical_reward smallint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_contact_opportunity_external_id UNIQUE (external_id),
    CONSTRAINT uq_contact_opportunity_source_event UNIQUE (source_event_id),
    CONSTRAINT fk_contact_opportunity_historical_channel
        FOREIGN KEY (historical_channel_id) REFERENCES contact_channel (channel_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT ck_contact_opportunity_external_id CHECK (external_id ~ '^OP-[0-9]{6,}$'),
    CONSTRAINT ck_contact_opportunity_month CHECK (month_code IN ('mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez')),
    CONSTRAINT ck_contact_opportunity_weekday CHECK (weekday_code IN ('seg', 'ter', 'qua', 'qui', 'sex')),
    CONSTRAINT ck_contact_opportunity_previous_outcome CHECK (previous_outcome_code IN ('fracasso', 'inexistente', 'sucesso')),
    CONSTRAINT ck_contact_opportunity_days CHECK (days_since_previous_contact BETWEEN 0 AND 27 OR days_since_previous_contact IS NULL),
    CONSTRAINT ck_contact_opportunity_previous_contacts CHECK (previous_campaign_contacts BETWEEN 0 AND 6),
    CONSTRAINT ck_contact_opportunity_attempts CHECK (current_campaign_previous_attempts BETWEEN 0 AND 55),
    CONSTRAINT ck_contact_opportunity_historical_reward CHECK (historical_reward IN (0, 1)),
    CONSTRAINT ck_contact_opportunity_contact_consistency CHECK (
        (never_contacted_before AND days_since_previous_contact IS NULL)
        OR (NOT never_contacted_before AND days_since_previous_contact IS NOT NULL)
    ),
    CONSTRAINT ck_contact_opportunity_permission CHECK (NOT do_not_contact OR NOT contact_authorized)
);

CREATE INDEX ix_contact_opportunity_created_at
    ON contact_opportunity (created_at DESC, opportunity_id DESC);

CREATE TABLE opportunity_eligible_channel (
    opportunity_id bigint NOT NULL,
    channel_id smallint NOT NULL,
    PRIMARY KEY (opportunity_id, channel_id),
    CONSTRAINT fk_opportunity_eligible_channel_opportunity
        FOREIGN KEY (opportunity_id) REFERENCES contact_opportunity (opportunity_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT fk_opportunity_eligible_channel_channel
        FOREIGN KEY (channel_id) REFERENCES contact_channel (channel_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE INDEX ix_opportunity_eligible_channel_channel
    ON opportunity_eligible_channel (channel_id, opportunity_id);

CREATE TABLE recommendation (
    recommendation_id uuid PRIMARY KEY,
    opportunity_id bigint NOT NULL,
    recommended_channel_id smallint NOT NULL,
    policy_id text NOT NULL,
    policy_version text NOT NULL,
    model_version text NOT NULL,
    is_exploration boolean NOT NULL,
    used_fallback boolean NOT NULL,
    causal_claim boolean NOT NULL DEFAULT false,
    uses_audit_only_attributes boolean NOT NULL DEFAULT false,
    reason text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL,
    CONSTRAINT fk_recommendation_opportunity
        FOREIGN KEY (opportunity_id) REFERENCES contact_opportunity (opportunity_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_recommendation_channel
        FOREIGN KEY (recommended_channel_id) REFERENCES contact_channel (channel_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT ck_recommendation_policy_id CHECK (btrim(policy_id) <> ''),
    CONSTRAINT ck_recommendation_policy_version CHECK (btrim(policy_version) <> ''),
    CONSTRAINT ck_recommendation_model_version CHECK (btrim(model_version) <> ''),
    CONSTRAINT ck_recommendation_reason CHECK (btrim(reason) <> ''),
    CONSTRAINT ck_recommendation_no_causal_claim CHECK (NOT causal_claim),
    CONSTRAINT ck_recommendation_no_audit_leakage CHECK (NOT uses_audit_only_attributes)
);

CREATE INDEX ix_recommendation_opportunity_created_at
    ON recommendation (opportunity_id, created_at DESC);

CREATE TABLE recommendation_feedback (
    recommendation_id uuid PRIMARY KEY,
    reward smallint NOT NULL,
    source text NOT NULL,
    observed_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    learning_applied boolean NOT NULL,
    upstream_status text NOT NULL,
    reason text NOT NULL,
    CONSTRAINT fk_recommendation_feedback_recommendation
        FOREIGN KEY (recommendation_id) REFERENCES recommendation (recommendation_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT ck_recommendation_feedback_reward CHECK (reward IN (0, 1)),
    CONSTRAINT ck_recommendation_feedback_source CHECK (source IN ('HISTORICAL', 'MANUAL')),
    CONSTRAINT ck_recommendation_feedback_status CHECK (upstream_status IN ('recorded', 'duplicate')),
    CONSTRAINT ck_recommendation_feedback_reason CHECK (btrim(reason) <> '')
);

COMMENT ON TABLE contact_opportunity IS
    'Oportunidades históricas. O canal e reward históricos são exclusivos de auditoria e simulação.';
COMMENT ON COLUMN contact_opportunity.historical_channel_id IS
    'Atributo pós-decisão; nunca deve ser enviado ao motor de recomendação.';
COMMENT ON COLUMN contact_opportunity.historical_reward IS
    'Resultado observado; nunca deve ser enviado ao motor de recomendação.';
COMMENT ON TABLE opportunity_eligible_channel IS
    'Relação N:N normalizada entre oportunidades e canais elegíveis.';
COMMENT ON COLUMN recommendation.causal_claim IS
    'Sempre falso: o dataset observacional não sustenta uma alegação causal.';
