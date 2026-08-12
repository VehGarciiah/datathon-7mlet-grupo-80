package br.com.fiap._mlet.datathon.grupo101.crm.api.opportunity.seed;

import java.io.IOException;
import java.io.InputStreamReader;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import java.util.ArrayList;
import java.util.List;
import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
public class OpportunityCsvImporter implements ApplicationRunner {

    private static final Logger LOGGER = LoggerFactory.getLogger(OpportunityCsvImporter.class);

    private static final String INSERT_OPPORTUNITY = """
            INSERT INTO contact_opportunity (
                external_id, source_event_id, month_code, weekday_code, previous_outcome_code,
                days_since_previous_contact, previous_campaign_contacts,
                current_campaign_previous_attempts, employment_variation_rate,
                consumer_price_index, consumer_confidence_index, euribor_3_months,
                employed_count, never_contacted_before, historical_channel_id, historical_reward
            )
            SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, channel_id, ?
            FROM contact_channel
            WHERE code = ?
            """;

    private final OpportunitySeedProperties properties;
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transaction;

    public OpportunityCsvImporter(
            OpportunitySeedProperties properties,
            JdbcTemplate jdbc,
            TransactionTemplate transaction) {
        this.properties = properties;
        this.jdbc = jdbc;
        this.transaction = transaction;
    }

    @Override
    public void run(ApplicationArguments args) throws IOException {
        if (!properties.enabled()) {
            LOGGER.info("Importação inicial de oportunidades desabilitada.");
            return;
        }

        Long currentCount = jdbc.queryForObject("SELECT count(*) FROM contact_opportunity", Long.class);
        if (currentCount != null && currentCount > 0) {
            LOGGER.info("Importação ignorada: {} oportunidades já persistidas.", currentCount);
            return;
        }
        if (!properties.csvLocation().exists()) {
            throw new IllegalStateException(
                    "CSV de oportunidades não encontrado em " + properties.csvLocation().getDescription());
        }

        List<SeedRow> rows = readRows();
        transaction.executeWithoutResult(status -> {
            jdbc.batchUpdate(INSERT_OPPORTUNITY, new SeedBatch(rows));
            jdbc.update("""
                    INSERT INTO opportunity_eligible_channel (opportunity_id, channel_id)
                    SELECT o.opportunity_id, c.channel_id
                    FROM contact_opportunity o
                    CROSS JOIN contact_channel c
                    """);
        });
        LOGGER.info("Importadas {} oportunidades históricas para o simulador de CRM.", rows.size());
    }

    private List<SeedRow> readRows() throws IOException {
        CSVFormat format = CSVFormat.DEFAULT.builder()
                .setDelimiter(';')
                .setHeader()
                .setSkipHeaderRecord(true)
                .get();
        try (var reader = new InputStreamReader(
                        properties.csvLocation().getInputStream(), StandardCharsets.UTF_8);
                CSVParser parser = format.parse(reader)) {
            List<SeedRow> rows = new ArrayList<>();
            for (CSVRecord record : parser) {
                rows.add(SeedRow.from(record));
            }
            return rows;
        }
    }

    private record SeedRow(
            long sourceEventId,
            String month,
            String weekday,
            String previousOutcome,
            Integer daysSincePreviousContact,
            int previousCampaignContacts,
            int currentCampaignPreviousAttempts,
            BigDecimal employmentVariationRate,
            BigDecimal consumerPriceIndex,
            BigDecimal consumerConfidenceIndex,
            BigDecimal euribor3Months,
            BigDecimal employedCount,
            boolean neverContactedBefore,
            int historicalReward,
            String historicalChannel
    ) {
        static SeedRow from(CSVRecord record) {
            long eventId = Long.parseLong(record.get("event_id"));
            String days = record.get("dias_desde_ultimo_contato");
            return new SeedRow(
                    eventId,
                    record.get("mes_contato"),
                    record.get("dia_semana"),
                    record.get("resultado_campanha_anterior"),
                    days.isBlank() ? null : new BigDecimal(days).intValueExact(),
                    Integer.parseInt(record.get("contatos_campanhas_anteriores")),
                    Integer.parseInt(record.get("tentativas_anteriores_campanha_atual")),
                    new BigDecimal(record.get("taxa_variacao_emprego")),
                    new BigDecimal(record.get("indice_precos_consumidor")),
                    new BigDecimal(record.get("indice_confianca_consumidor")),
                    new BigDecimal(record.get("euribor_3_meses")),
                    new BigDecimal(record.get("numero_empregados")),
                    "1".equals(record.get("nunca_contatado_anteriormente")),
                    Integer.parseInt(record.get("resultado")),
                    record.get("canal_contato"));
        }
    }

    private static final class SeedBatch implements BatchPreparedStatementSetter {

        private final List<SeedRow> rows;

        private SeedBatch(List<SeedRow> rows) {
            this.rows = rows;
        }

        @Override
        public void setValues(PreparedStatement ps, int index) throws SQLException {
            SeedRow row = rows.get(index);
            ps.setString(1, "OP-%06d".formatted(row.sourceEventId()));
            ps.setLong(2, row.sourceEventId());
            ps.setString(3, row.month());
            ps.setString(4, row.weekday());
            ps.setString(5, row.previousOutcome());
            if (row.daysSincePreviousContact() == null) {
                ps.setNull(6, Types.SMALLINT);
            } else {
                ps.setInt(6, row.daysSincePreviousContact());
            }
            ps.setInt(7, row.previousCampaignContacts());
            ps.setInt(8, row.currentCampaignPreviousAttempts());
            ps.setBigDecimal(9, row.employmentVariationRate());
            ps.setBigDecimal(10, row.consumerPriceIndex());
            ps.setBigDecimal(11, row.consumerConfidenceIndex());
            ps.setBigDecimal(12, row.euribor3Months());
            ps.setBigDecimal(13, row.employedCount());
            ps.setBoolean(14, row.neverContactedBefore());
            ps.setInt(15, row.historicalReward());
            ps.setString(16, row.historicalChannel());
        }

        @Override
        public int getBatchSize() {
            return rows.size();
        }
    }
}
