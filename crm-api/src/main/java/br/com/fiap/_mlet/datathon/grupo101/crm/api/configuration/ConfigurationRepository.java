package br.com.fiap._mlet.datathon.grupo101.crm.api.configuration;

import br.com.fiap._mlet.datathon.grupo101.crm.api.configuration.dto.ActivateConfigurationRequest;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class ConfigurationRepository {

    private static final String SELECT_COLUMNS = """
            SELECT version, policy_mode, kill_switch, adaptive_traffic_percentage,
                   experiment_name, deterministic_allocation, learning_enabled,
                   attribution_window_days, structured_logs, decision_metrics,
                   feedback_metrics, configuration_audit, trace_sampling_percentage,
                   activated_by, activation_reason, activated_at
            FROM runtime_configuration
            """;

    private final JdbcClient jdbc;

    public ConfigurationRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public RuntimeConfiguration findActive() {
        return jdbc.sql(SELECT_COLUMNS + " ORDER BY version DESC LIMIT 1")
                .query(this::map)
                .single();
    }

    public List<RuntimeConfiguration> findHistory(int limit) {
        return jdbc.sql(SELECT_COLUMNS + " ORDER BY version DESC LIMIT :limit")
                .param("limit", limit)
                .query(this::map)
                .list();
    }

    public void acquireActivationLock() {
        jdbc.sql("SELECT pg_advisory_xact_lock(7100101)")
                .query((resultSet, rowNumber) -> rowNumber)
                .single();
    }

    public RuntimeConfiguration insert(long version, ActivateConfigurationRequest request) {
        jdbc.sql("""
                        INSERT INTO runtime_configuration (
                            version, policy_mode, kill_switch, adaptive_traffic_percentage,
                            experiment_name, deterministic_allocation, learning_enabled,
                            attribution_window_days, structured_logs, decision_metrics,
                            feedback_metrics, configuration_audit, trace_sampling_percentage,
                            activated_by, activation_reason
                        ) VALUES (
                            :version, :policyMode, :killSwitch, :traffic,
                            :experimentName, :deterministicAllocation, :learningEnabled,
                            :attributionWindowDays, :structuredLogs, :decisionMetrics,
                            :feedbackMetrics, :configurationAudit, :traceSampling,
                            :operator, :reason
                        )
                        """)
                .param("version", version)
                .param("policyMode", request.policyMode())
                .param("killSwitch", request.killSwitch())
                .param("traffic", request.adaptiveTrafficPercentage())
                .param("experimentName", request.experimentName().trim())
                .param("deterministicAllocation", request.deterministicAllocation())
                .param("learningEnabled", request.learningEnabled())
                .param("attributionWindowDays", request.attributionWindowDays())
                .param("structuredLogs", request.structuredLogs())
                .param("decisionMetrics", request.decisionMetrics())
                .param("feedbackMetrics", request.feedbackMetrics())
                .param("configurationAudit", request.configurationAudit())
                .param("traceSampling", request.traceSamplingPercentage())
                .param("operator", request.operator().trim())
                .param("reason", request.reason().trim())
                .update();
        return jdbc.sql(SELECT_COLUMNS + " WHERE version = :version")
                .param("version", version)
                .query(this::map)
                .single();
    }

    private RuntimeConfiguration map(ResultSet resultSet, int rowNumber) throws SQLException {
        return new RuntimeConfiguration(
                resultSet.getLong("version"),
                resultSet.getString("policy_mode"),
                resultSet.getBoolean("kill_switch"),
                resultSet.getInt("adaptive_traffic_percentage"),
                resultSet.getString("experiment_name"),
                resultSet.getBoolean("deterministic_allocation"),
                resultSet.getBoolean("learning_enabled"),
                resultSet.getInt("attribution_window_days"),
                resultSet.getBoolean("structured_logs"),
                resultSet.getBoolean("decision_metrics"),
                resultSet.getBoolean("feedback_metrics"),
                resultSet.getBoolean("configuration_audit"),
                resultSet.getInt("trace_sampling_percentage"),
                resultSet.getString("activated_by"),
                resultSet.getString("activation_reason"),
                resultSet.getObject("activated_at", OffsetDateTime.class));
    }
}
