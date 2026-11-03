-- Apply once after 004, in a transaction. Existing tasks keep NULL.

ALTER TABLE tasks
    ADD COLUMN duration_minutes INTEGER
        CONSTRAINT tasks_duration_not_negative CHECK (duration_minutes >= 0);
