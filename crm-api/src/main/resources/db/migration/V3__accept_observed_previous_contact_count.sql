ALTER TABLE contact_opportunity
    DROP CONSTRAINT ck_contact_opportunity_previous_contacts;

ALTER TABLE contact_opportunity
    ADD CONSTRAINT ck_contact_opportunity_previous_contacts
    CHECK (previous_campaign_contacts BETWEEN 0 AND 7);

COMMENT ON COLUMN contact_opportunity.previous_campaign_contacts IS
    'Faixa observada no conjunto processado completo; o valor 7 ocorre uma vez no teste e pode ser rejeitado pelo contrato pré-decisão treinado.';
