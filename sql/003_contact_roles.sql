-- Apply once after 002, in a transaction while the application is stopped.
-- Preserve every old name before dropping recipient. Ambiguous contacts go
-- provisionally into other, to be classified by the user when editing.
ALTER TABLE tasks
    DROP CONSTRAINT tasks_parties_consistent,
    DROP CONSTRAINT tasks_order_progress_consistent,
    ADD COLUMN other TEXT;

UPDATE tasks SET customer = recipient
WHERE task_type = 'quotation' AND recipient IS NOT NULL;

UPDATE tasks SET supplier = recipient
WHERE task_type = 'price_request' AND recipient IS NOT NULL;

UPDATE tasks SET other = recipient
WHERE task_type NOT IN ('quotation', 'price_request') AND recipient IS NOT NULL;

ALTER TABLE tasks DROP COLUMN recipient;
ALTER TABLE tasks
    ADD CONSTRAINT tasks_customer_check CHECK (customer ~ '[^[:space:]]'),
    ADD CONSTRAINT tasks_supplier_check CHECK (supplier ~ '[^[:space:]]'),
    ADD CONSTRAINT tasks_other_check CHECK (other ~ '[^[:space:]]');

-- Old orders need classification and confirmation of delivery progress.
-- NOT VALID keeps those rows; every new or edited row follows the new rules.
ALTER TABLE tasks ADD CONSTRAINT tasks_parties_consistent CHECK (
    (task_type = 'order' AND customer IS NOT NULL AND supplier IS NOT NULL AND other IS NULL)
    OR (task_type <> 'order' AND num_nonnulls(customer, supplier, other) = 1
        AND (task_type <> 'quotation' OR customer IS NOT NULL)
        AND (task_type <> 'price_request' OR supplier IS NOT NULL))
) NOT VALID;

ALTER TABLE tasks ADD CONSTRAINT tasks_order_progress_consistent CHECK (
    (task_type = 'order'
     AND (NOT order_delivered OR order_placed)
     AND order_delivered = (status = 'completed'))
    OR (task_type <> 'order' AND NOT order_placed AND NOT order_delivered)
) NOT VALID;
