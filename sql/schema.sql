CREATE TABLE IF NOT EXISTS tasks (
    task_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_type TEXT NOT NULL
        CHECK (task_type IN (
            'email', 'phone_call', 'order',
            'follow_up', 'quotation', 'other')),
    recipient TEXT NOT NULL -- person or organization associated with the task
        CONSTRAINT tasks_recipient_not_blank CHECK (recipient ~ '[^[:space:]]'),
    description TEXT NOT NULL
        CONSTRAINT tasks_description_not_blank CHECK (description ~ '[^[:space:]]'),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'completed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    CONSTRAINT tasks_completion_consistent CHECK (
        (status = 'completed' AND completed_at IS NOT NULL)
        OR (status <> 'completed' AND completed_at IS NULL)
    )
);
