package br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity;

import java.sql.Array;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class OpportunityRepository {

    private static final String SELECT_COLUMNS = """
            SELECT o.opportunity_id, o.external_id, o.source_event_id, o.month_code,
                   o.weekday_code, o.previous_outcome_code, o.days_since_previous_contact,
                   o.previous_campaign_contacts, o.current_campaign_previous_attempts,
                   o.employment_variation_rate, o.consumer_price_index,
                   o.consumer_confidence_index, o.euribor_3_months, o.employed_count,
                   o.never_contacted_before, o.contact_authorized, o.do_not_contact,
                   ARRAY(
                       SELECT c.code
                       FROM opportunity_eligible_channel ec
                       JOIN contact_channel c ON c.channel_id = ec.channel_id
                       WHERE ec.opportunity_id = o.opportunity_id
                       ORDER BY c.channel_id
                   ) AS eligible_channels,
                   hc.code AS historical_channel, o.historical_reward, o.created_at
            FROM contact_opportunity o
            JOIN contact_channel hc ON hc.channel_id = o.historical_channel_id
            """;

    private final JdbcClient jdbc;

    public OpportunityRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public List<Opportunity> findPage(String search, int limit, int offset) {
        String normalized = search == null ? "" : search.strip();
        return jdbc.sql(SELECT_COLUMNS + """
                        WHERE (:search = '' OR o.external_id ILIKE '%' || :search || '%')
                        ORDER BY o.opportunity_id
                        LIMIT :limit OFFSET :offset
                        """)
                .param("search", normalized)
                .param("limit", limit)
                .param("offset", offset)
                .query(this::map)
                .list();
    }

    public long count(String search) {
        String normalized = search == null ? "" : search.strip();
        return jdbc.sql("""
                        SELECT count(*)
                        FROM contact_opportunity
                        WHERE (:search = '' OR external_id ILIKE '%' || :search || '%')
                        """)
                .param("search", normalized)
                .query(Long.class)
                .single();
    }

    public Optional<Opportunity> findById(long id) {
        return jdbc.sql(SELECT_COLUMNS + " WHERE o.opportunity_id = :id")
                .param("id", id)
                .query(this::map)
                .optional();
    }

    public void updateEligibility(
            long id, boolean contactAuthorized, boolean doNotContact, List<String> eligibleChannels) {
        jdbc.sql("""
                        UPDATE contact_opportunity
                        SET contact_authorized = :authorized, do_not_contact = :doNotContact
                        WHERE opportunity_id = :id
                        """)
                .param("authorized", contactAuthorized)
                .param("doNotContact", doNotContact)
                .param("id", id)
                .update();

        jdbc.sql("DELETE FROM opportunity_eligible_channel WHERE opportunity_id = :id")
                .param("id", id)
                .update();
        for (String channel : eligibleChannels) {
            jdbc.sql("""
                            INSERT INTO opportunity_eligible_channel (opportunity_id, channel_id)
                            SELECT :id, channel_id FROM contact_channel WHERE code = :code
                            """)
                    .param("id", id)
                    .param("code", channel)
                    .update();
        }
    }

    private Opportunity map(ResultSet rs, int rowNumber) throws SQLException {
        Array sqlArray = rs.getArray("eligible_channels");
        List<String> eligibleChannels = Arrays.asList((String[]) sqlArray.getArray());
        return new Opportunity(
                rs.getLong("opportunity_id"),
                rs.getString("external_id"),
                rs.getLong("source_event_id"),
                rs.getString("month_code"),
                rs.getString("weekday_code"),
                rs.getString("previous_outcome_code"),
                rs.getObject("days_since_previous_contact", Integer.class),
                rs.getInt("previous_campaign_contacts"),
                rs.getInt("current_campaign_previous_attempts"),
                rs.getBigDecimal("employment_variation_rate"),
                rs.getBigDecimal("consumer_price_index"),
                rs.getBigDecimal("consumer_confidence_index"),
                rs.getBigDecimal("euribor_3_months"),
                rs.getBigDecimal("employed_count"),
                rs.getBoolean("never_contacted_before"),
                rs.getBoolean("contact_authorized"),
                rs.getBoolean("do_not_contact"),
                eligibleChannels,
                rs.getString("historical_channel"),
                rs.getInt("historical_reward"),
                rs.getTimestamp("created_at").toInstant());
    }
}
