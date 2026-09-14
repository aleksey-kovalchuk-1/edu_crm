-- Run once after the API has initialized its tables.
-- Only aggregated demonstration statistics are exposed to the BI account.
CREATE ROLE analytics_reader LOGIN PASSWORD 'local-analytics-only';
GRANT CONNECT ON DATABASE edu_crm TO analytics_reader;
GRANT USAGE ON SCHEMA public TO analytics_reader;
CREATE VIEW analytics_annual AS
SELECT year, applications, students, streams FROM annual_metrics;
GRANT SELECT ON analytics_annual TO analytics_reader;
