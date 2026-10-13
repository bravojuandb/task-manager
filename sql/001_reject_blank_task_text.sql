-- Apply once to an existing tasks table. Existing blank values cause failure.
ALTER TABLE tasks
    ADD CONSTRAINT tasks_recipient_not_blank
        CHECK (recipient ~ '[^[:space:]]'),
    ADD CONSTRAINT tasks_description_not_blank
        CHECK (description ~ '[^[:space:]]');
