package br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation;

import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.client.RecommendationApiClient.FeedbackDecision;
import br.com.fiap._mlet.datathon.grupo101.crm.api.recommendation.client.RecommendationApiClient.RecommendationDecision;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import tools.jackson.core.JacksonException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

@Repository
public class RecommendationRepository {

    private static final String SELECT_COLUMNS = """
            SELECT r.recommendation_id, r.opportunity_id, o.external_id,
                   rc.code AS recommended_channel, r.policy_id, r.policy_version,
                   r.model_version, r.is_exploration, r.used_fallback, r.reason,
                   r.evidence::text AS evidence, r.created_at,
                   hc.code AS historical_channel, o.historical_reward,
                   rf.reward AS feedback_reward, rf.source AS feedback_source,
                   rf.observed_at AS feedback_observed_at,
                   rf.received_at AS feedback_received_at,
                   rf.learning_applied AS feedback_learning_applied,
                   rf.upstream_status AS feedback_upstream_status,
                   rf.reason AS feedback_reason
            FROM recommendation r
            JOIN contact_opportunity o ON o.opportunity_id = r.opportunity_id
            JOIN contact_channel rc ON rc.channel_id = r.recommended_channel_id
            JOIN contact_channel hc ON hc.channel_id = o.historical_channel_id
            LEFT JOIN recommendation_feedback rf
                   ON rf.recommendation_id = r.recommendation_id
            """;

    private final JdbcClient jdbc;
    private final ObjectMapper objectMapper;

    public RecommendationRepository(JdbcClient jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    public void save(long opportunityId, RecommendationDecision decision) {
        jdbc.sql("""
                        INSERT INTO recommendation (
                            recommendation_id, opportunity_id, recommended_channel_id,
                            policy_id, policy_version, model_version, is_exploration,
                            used_fallback, reason, evidence, created_at
                        )
                        SELECT :id, :opportunityId, channel_id, :policyId, :policyVersion,
                               :modelVersion, :exploration, :fallback, :reason,
                               CAST(:evidence AS jsonb), :createdAt
                        FROM contact_channel
                        WHERE code = :channel
                        """)
                .param("id", decision.recommendationId())
                .param("opportunityId", opportunityId)
                .param("policyId", decision.policyId())
                .param("policyVersion", decision.policyVersion())
                .param("modelVersion", decision.modelVersion())
                .param("exploration", decision.exploration())
                .param("fallback", decision.usedFallback())
                .param("reason", decision.reason())
                .param("evidence", toJson(decision.evidence()))
                .param("createdAt", decision.createdAt())
                .param("channel", decision.recommendedAction())
                .update();
    }

    public Optional<StoredRecommendation> findById(UUID id) {
        return jdbc.sql(SELECT_COLUMNS + " WHERE r.recommendation_id = :id")
                .param("id", id)
                .query(this::map)
                .optional();
    }

    public List<StoredRecommendation> findByOpportunityId(long opportunityId) {
        return jdbc.sql(SELECT_COLUMNS + """
                        WHERE r.opportunity_id = :opportunityId
                        ORDER BY r.created_at DESC, r.recommendation_id DESC
                        """)
                .param("opportunityId", opportunityId)
                .query(this::map)
                .list();
    }

    public void saveFeedback(
            UUID recommendationId,
            int reward,
            String source,
            OffsetDateTime observedAt,
            FeedbackDecision decision) {
        jdbc.sql("""
                        INSERT INTO recommendation_feedback (
                            recommendation_id, reward, source, observed_at,
                            learning_applied, upstream_status, reason
                        ) VALUES (
                            :id, :reward, :source, :observedAt,
                            :learningApplied, :status, :reason
                        )
                        ON CONFLICT (recommendation_id) DO NOTHING
                        """)
                .param("id", recommendationId)
                .param("reward", reward)
                .param("source", source)
                .param("observedAt", observedAt)
                .param("learningApplied", decision.learningApplied())
                .param("status", decision.status())
                .param("reason", decision.reason())
                .update();
    }

    public boolean hasFeedback(UUID recommendationId) {
        return jdbc.sql("SELECT EXISTS (SELECT 1 FROM recommendation_feedback WHERE recommendation_id = :id)")
                .param("id", recommendationId)
                .query(Boolean.class)
                .single();
    }

    private StoredRecommendation map(ResultSet rs, int rowNumber) throws SQLException {
        Integer feedbackReward = rs.getObject("feedback_reward", Integer.class);
        RecommendationFeedback feedback = feedbackReward == null
                ? null
                : new RecommendationFeedback(
                        feedbackReward,
                        rs.getString("feedback_source"),
                        rs.getObject("feedback_observed_at", OffsetDateTime.class),
                        rs.getObject("feedback_received_at", OffsetDateTime.class),
                        rs.getBoolean("feedback_learning_applied"),
                        rs.getString("feedback_upstream_status"),
                        rs.getString("feedback_reason"));
        return new StoredRecommendation(
                rs.getObject("recommendation_id", UUID.class),
                rs.getLong("opportunity_id"),
                rs.getString("external_id"),
                rs.getString("recommended_channel"),
                rs.getString("policy_id"),
                rs.getString("policy_version"),
                rs.getString("model_version"),
                rs.getBoolean("is_exploration"),
                rs.getBoolean("used_fallback"),
                rs.getString("reason"),
                fromJson(rs.getString("evidence")),
                rs.getObject("created_at", OffsetDateTime.class),
                rs.getString("historical_channel"),
                rs.getInt("historical_reward"),
                feedback);
    }

    private String toJson(Map<String, Object> value) {
        try {
            return objectMapper.writeValueAsString(value == null ? Map.of() : value);
        } catch (JacksonException exception) {
            throw new IllegalArgumentException("Evidence inválida retornada pelo motor.", exception);
        }
    }

    private Map<String, Object> fromJson(String value) {
        try {
            return objectMapper.readValue(value, new TypeReference<>() { });
        } catch (JacksonException exception) {
            throw new IllegalStateException("Evidence persistida não pôde ser lida.", exception);
        }
    }
}
