-- Apply once after 003, in a transaction. No task data is changed.
ALTER TABLE tasks DROP CONSTRAINT tasks_parties_consistent;
ALTER TABLE tasks ADD CONSTRAINT tasks_parties_consistent CHECK (
    (task_type = 'order' AND customer IS NOT NULL AND supplier IS NOT NULL AND other IS NULL)
    OR (task_type <> 'order' AND num_nonnulls(customer, supplier, other) >= 1)
) NOT VALID;
-- Old orders still require classification; new/updated rows are checked.
