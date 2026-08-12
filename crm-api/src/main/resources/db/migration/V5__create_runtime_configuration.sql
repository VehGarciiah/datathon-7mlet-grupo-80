CREATE TABLE runtime_configuration (
    configuration_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version bigint NOT NULL,
    policy_mode text NOT NULL,
    kill_switch boolean NOT NULL,
    adaptive_traffic_percentage smallint NOT NULL,
    experiment_name text NOT NULL DEFAULT '',
    deterministic_allocation boolean NOT NULL,
    learning_enabled boolean NOT NULL,
    attribution_window_days smallint NOT NULL,
    structured_logs boolean NOT NULL,
    decision_metrics boolean NOT NULL,
    feedback_metrics boolean NOT NULL,
    configuration_audit boolean NOT NULL,
    trace_sampling_percentage smallint NOT NULL,
    activated_by text NOT NULL,
    activation_reason text NOT NULL,
    activated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_runtime_configuration_version UNIQUE (version),
    CONSTRAINT ck_runtime_configuration_version CHECK (version > 0),
    CONSTRAINT ck_runtime_configuration_policy_mode
        CHECK (policy_mode IN ('approved', 'approved_adaptive', 'adaptive_demo')),
    CONSTRAINT ck_runtime_configuration_traffic
        CHECK (adaptive_traffic_percentage BETWEEN 0 AND 100),
    CONSTRAINT ck_runtime_configuration_attribution
        CHECK (attribution_window_days BETWEEN 1 AND 30),
    CONSTRAINT ck_runtime_configuration_trace_sampling
        CHECK (trace_sampling_percentage BETWEEN 0 AND 100),
    CONSTRAINT ck_runtime_configuration_actor CHECK (btrim(activated_by) <> ''),
    CONSTRAINT ck_runtime_configuration_reason CHECK (btrim(activation_reason) <> ''),
    CONSTRAINT ck_runtime_configuration_adaptive_consistency CHECK (
        (policy_mode = 'approved' AND adaptive_traffic_percentage = 0 AND NOT learning_enabled)
        OR (
            policy_mode IN ('approved_adaptive', 'adaptive_demo')
            AND adaptive_traffic_percentage > 0
            AND btrim(experiment_name) <> ''
        )
    ),
    CONSTRAINT ck_runtime_configuration_kill_switch CHECK (
        NOT kill_switch
        OR (policy_mode = 'approved' AND adaptive_traffic_percentage = 0 AND NOT learning_enabled)
    )
);

CREATE INDEX ix_runtime_configuration_activated_at
    ON runtime_configuration (activated_at DESC, configuration_id DESC);

INSERT INTO runtime_configuration (
    version, policy_mode, kill_switch, adaptive_traffic_percentage,
    experiment_name, deterministic_allocation, learning_enabled,
    attribution_window_days, structured_logs, decision_metrics,
    feedback_metrics, configuration_audit, trace_sampling_percentage,
    activated_by, activation_reason
) VALUES (
    1, 'approved', false, 0,
    '', true, false,
    7, true, true,
    true, true, 10,
    'system', 'Configuração inicial segura criada pela migration.'
);

COMMENT ON TABLE runtime_configuration IS
    'Histórico imutável das configurações operacionais publicadas ao flagd.';

GRANT SELECT, INSERT ON TABLE runtime_configuration TO crm_app;
GRANT USAGE, SELECT ON SEQUENCE runtime_configuration_configuration_id_seq TO crm_app;
