CREATE TABLE IF NOT EXISTS ue_agent_store (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO ue_agent_store (id, payload)
VALUES (
    1,
    '{"projects": [], "calculationSnapshots": [], "dataSources": [], "policyDocuments": [], "policyFacts": []}'::jsonb
)
ON CONFLICT (id) DO NOTHING;
