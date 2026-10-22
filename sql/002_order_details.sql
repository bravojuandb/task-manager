-- Apply once, inside a transaction. Existing recipients are preserved.
ALTER TABLE tasks
    ADD COLUMN customer TEXT,
    ADD COLUMN supplier TEXT,
    ADD COLUMN order_placed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN order_delivered BOOLEAN NOT NULL DEFAULT FALSE,
    ALTER COLUMN recipient DROP NOT NULL;

ALTER TABLE tasks DROP CONSTRAINT tasks_task_type_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_task_type_check CHECK (
    task_type IN ('email', 'phone_call', 'order', 'follow_up', 'quotation', 'price_request', 'other')
);

-- NOT VALID preserves old orders whose customer/supplier are not yet known.
-- Both constraints still apply to every new or updated row immediately.
-- Editing an old order must supply the real parties and its delivery flags.
ALTER TABLE tasks ADD CONSTRAINT tasks_parties_consistent CHECK (
    (task_type = 'order' AND recipient IS NULL
     AND customer IS NOT NULL AND customer ~ '[^[:space:]]'
     AND supplier IS NOT NULL AND supplier ~ '[^[:space:]]')
    OR (task_type <> 'order' AND recipient IS NOT NULL
        AND customer IS NULL AND supplier IS NULL)
) NOT VALID;

ALTER TABLE tasks ADD CONSTRAINT tasks_order_progress_consistent CHECK (
    (task_type = 'order'
     AND (NOT order_delivered OR order_placed)
     AND order_delivered = (status = 'completed'))
    OR (task_type <> 'order' AND NOT order_placed AND NOT order_delivered)
) NOT VALID;

-- Once all legacy orders have been edited, run:
-- ALTER TABLE tasks VALIDATE CONSTRAINT tasks_parties_consistent;
-- ALTER TABLE tasks VALIDATE CONSTRAINT tasks_order_progress_consistent;
