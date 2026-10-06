-- What the odds and "realistic MW ahead" need beyond ticket "Load and organise the data".
-- See docs/specs/product-spec.md, ticket "Chances, waits, and who's ahead".

-- The MW a project would send to the grid, as the operator states it (main report: "Net MWs
-- to Grid"; 2023-batch report: "NET MW POI"). A hybrid lists each part's MW separately
-- (200 MW solar + 200 MW battery), so adding up project_resources would count it twice.
ALTER TABLE projects ADD COLUMN mw_to_grid double precision;

-- The day each source's data was taken: a project still waiting is known to be waiting up
-- to this day, never up to the day the analysis runs.
CREATE TABLE data_as_of (
    source    source PRIMARY KEY,
    as_of     date NOT NULL,
    read_from text NOT NULL  -- where the date was read, to cite
);

-- The per-source views were created with SELECT *, which Postgres expands once; recreate
-- them so they carry the new column. Definitions otherwise unchanged from 0002.
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
