-- What the public site's limits need: what each model call cost, and when write-ups were
-- started and by whom. See interconnection_agent.spending and interconnection_agent.api.write_ups.

-- One row per model call, priced from the tokens it used at its model's rates.
CREATE TABLE model_spend (
    at    timestamptz NOT NULL,
    model text NOT NULL,
    usd   numeric(12, 6) NOT NULL
);
CREATE INDEX model_spend_at ON model_spend (at);

-- One row per write-up started. The visitor is a keyed hash of their internet address,
-- never the address itself; rows older than two days are deleted.
CREATE TABLE write_up_starts (
    at      timestamptz NOT NULL,
    visitor text NOT NULL
);
CREATE INDEX write_up_starts_at ON write_up_starts (at);

-- The key for those hashes: made once, at random, and kept so counts survive a restart.
CREATE TABLE visitor_key (
    only_row boolean PRIMARY KEY DEFAULT true CHECK (only_row),
    key      bytea NOT NULL
);
