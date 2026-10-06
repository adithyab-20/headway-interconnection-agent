-- What the numbers need beyond the raw queue: how far each project got, a usable outcome
-- date, where each project connects, where those places are on the map, and the costs and
-- planned upgrades around them. See docs/specs/product-spec.md, ticket "Load and organise
-- the data".

-- How far each project got, and which batch it applied in. CAISO only; LBNL leaves these
-- empty. estimated_outcome_date is filled only when the real outcome date is missing; the
-- real date columns are never overwritten.
ALTER TABLE projects
    ADD COLUMN batch                  text,
    ADD COLUMN furthest_step          text,
    ADD COLUMN deliverability         text,
    ADD COLUMN agreement_status       text,
    ADD COLUMN estimated_outcome_date date;

-- The per-source views were created with SELECT *, which Postgres expands once; recreate
-- them so they carry the new columns, plus the outcome date the analysis uses.
DROP VIEW caiso_projects;
DROP VIEW lbnl_projects;

CREATE VIEW caiso_projects AS
SELECT p.*,
       coalesce(p.actual_online_date, p.withdrawn_date, p.estimated_outcome_date) AS outcome_date,
       (p.actual_online_date IS NULL AND p.withdrawn_date IS NULL
        AND p.estimated_outcome_date IS NOT NULL)                                 AS outcome_date_estimated,
       coalesce(p.actual_online_date, p.withdrawn_date) < p.q_date                AS outcome_before_entry
FROM projects p WHERE p.source = 'caiso_raw';

CREATE VIEW lbnl_projects AS
SELECT p.*,
       coalesce(p.actual_online_date, p.withdrawn_date, p.estimated_outcome_date) AS outcome_date,
       (p.actual_online_date IS NULL AND p.withdrawn_date IS NULL
        AND p.estimated_outcome_date IS NOT NULL)                                 AS outcome_date_estimated,
       coalesce(p.actual_online_date, p.withdrawn_date) < p.q_date                AS outcome_before_entry
FROM projects p WHERE p.source = 'lbnl';

-- A place is one voltage section of a substation site, e.g. "Birds Landing 230 kV".
-- Position comes from OpenStreetMap through a reviewed match, else the place falls back
-- to its county (positioned_by = 'county', no coordinates).
CREATE TABLE places (
    place         text PRIMARY KEY,
    site          text NOT NULL,
    voltage_kv    integer,
    county        text,
    state         text,
    latitude      double precision,
    longitude     double precision,
    positioned_by text NOT NULL CHECK (positioned_by IN ('openstreetmap', 'county')),
    osm_id        text,
    osm_date      date,
    osm_county    text   -- county the OpenStreetMap point falls in, checked at review
);

-- Where each project connects. 'at' = at the place; 'line_end' = partway along a line,
-- counted at both of the line's end places.
CREATE TABLE project_places (
    source    source NOT NULL,
    native_id text   NOT NULL,
    place     text   NOT NULL REFERENCES places (place),
    role      text   NOT NULL CHECK (role IN ('at', 'line_end')),
    PRIMARY KEY (source, native_id, place),
    FOREIGN KEY (source, native_id) REFERENCES projects (source, native_id) ON DELETE CASCADE
);

-- Bottlenecks: overloaded lines or transformers that several places sit behind (operator's
-- 2024 list), with the next upgrade's added room and cost (operator's 2026 estimates).
CREATE TABLE bottlenecks (
    bottleneck      text PRIMARY KEY,
    room_left_mw    double precision,  -- MW still available behind it (2024 list)
    added_mw        double precision,
    cost_musd_2022  double precision,  -- millions of US dollars, 2022 prices
    listed_in       text NOT NULL DEFAULT 'CAISO bottleneck list, 2024 edition',
    costed_in       text  -- 'CAISO transmission capability estimates, 2026', when costed
);

CREATE TABLE place_bottleneck_links (
    place      text NOT NULL REFERENCES places (place),
    bottleneck text NOT NULL REFERENCES bottlenecks (bottleneck),
    PRIMARY KEY (place, bottleneck)
);

CREATE VIEW place_bottlenecks AS
SELECT l.place, b.bottleneck, b.room_left_mw, b.added_mw, b.cost_musd_2022, b.listed_in,
       b.costed_in,
       b.cost_musd_2022 * 1e6 / nullif(b.added_mw * 1000, 0) AS cost_per_kw_2022
FROM place_bottleneck_links l JOIN bottlenecks b USING (bottleneck);

-- Planned grid upgrades from the operator's yearly plan. Paid by all electricity customers,
-- never by the projects connecting nearby.
CREATE TABLE upgrades (
    plan_id         text PRIMARY KEY,
    name            text NOT NULL,
    utility         text,
    expected_finish      date,     -- when the plan gives a full date
    expected_finish_year integer,  -- always, even when the plan gives only a year
    cost_low_musd   double precision,
    cost_high_musd  double precision,
    source          text NOT NULL,  -- the operator documents this row came from
    fact_sheet_page integer          -- page of the plan's fact sheets with the cost, if any
);

CREATE TABLE upgrade_places (
    plan_id text NOT NULL REFERENCES upgrades (plan_id),
    place   text NOT NULL REFERENCES places (place),
    PRIMARY KEY (plan_id, place)
);

CREATE VIEW planned_upgrades AS
SELECT u.*, up.place, 'all electricity customers'::text AS paid_by
FROM upgrades u LEFT JOIN upgrade_places up USING (plan_id);
