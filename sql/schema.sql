CREATE TABLE IF NOT EXISTS tasks (
    task_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_type TEXT NOT NULL
        CHECK (task_type IN (
            'email', 'phone_call', 'order',
            'follow_up', 'quotation', 'price_request', 'other')),
    description TEXT NOT NULL
        CONSTRAINT tasks_description_not_blank CHECK (description ~ '[^[:space:]]'),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'completed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    customer TEXT CHECK (customer ~ '[^[:space:]]'),
    supplier TEXT CHECK (supplier ~ '[^[:space:]]'),
    other TEXT CHECK (other ~ '[^[:space:]]'),
    order_placed BOOLEAN NOT NULL DEFAULT FALSE,
    order_delivered BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT tasks_parties_consistent CHECK (
        (task_type = 'order' AND customer IS NOT NULL AND supplier IS NOT NULL AND other IS NULL)
        OR (task_type <> 'order' AND num_nonnulls(customer, supplier, other) >= 1)
    ),
    CONSTRAINT tasks_order_progress_consistent CHECK (
        (task_type = 'order'
         AND (NOT order_delivered OR order_placed)
         AND order_delivered = (status = 'completed'))
        OR (task_type <> 'order' AND NOT order_placed AND NOT order_delivered)
    ),
    CONSTRAINT tasks_completion_consistent CHECK (
        (status = 'completed' AND completed_at IS NOT NULL)
        OR (status <> 'completed' AND completed_at IS NULL)
    )
);
