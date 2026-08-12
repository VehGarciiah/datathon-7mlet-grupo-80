ALTER TABLE contact_opportunity
    ADD CONSTRAINT ck_contact_opportunity_employment_variation
        CHECK (employment_variation_rate BETWEEN -3.4 AND 1.4),
    ADD CONSTRAINT ck_contact_opportunity_consumer_price
        CHECK (consumer_price_index BETWEEN 92.201 AND 94.767),
    ADD CONSTRAINT ck_contact_opportunity_consumer_confidence
        CHECK (consumer_confidence_index BETWEEN -50.8 AND -26.9),
    ADD CONSTRAINT ck_contact_opportunity_euribor
        CHECK (euribor_3_months BETWEEN 0.634 AND 5.045),
    ADD CONSTRAINT ck_contact_opportunity_employed_count
        CHECK (employed_count BETWEEN 4963.6 AND 5228.1);

GRANT USAGE ON SCHEMA crm TO crm_app;
GRANT SELECT ON TABLE contact_channel TO crm_app;
GRANT SELECT, INSERT, UPDATE ON TABLE contact_opportunity TO crm_app;
GRANT SELECT, INSERT, DELETE ON TABLE opportunity_eligible_channel TO crm_app;
GRANT SELECT, INSERT ON TABLE recommendation TO crm_app;
GRANT SELECT, INSERT ON TABLE recommendation_feedback TO crm_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA crm TO crm_app;
