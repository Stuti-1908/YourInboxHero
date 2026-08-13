CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- for gen_random_uuid()

CREATE TABLE debtor (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    debtor_type TEXT NOT NULL CHECK (debtor_type IN ('business'))
);

CREATE TABLE invoice (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    debtor_id UUID NOT NULL REFERENCES debtor(id) ON DELETE CASCADE,
    invoice_number TEXT NOT NULL UNIQUE,
    amount NUMERIC(12,2) NOT NULL,
    description TEXT,
    due_date DATE NOT NULL,
    payment_instructions TEXT,
    status TEXT NOT NULL CHECK (status IN ('upcoming','due','overdue','paid','manual','paused')),
    last_reminder_sent TIMESTAMP
);

CREATE TABLE reminder_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID NOT NULL REFERENCES invoice(id),
    sent_at TIMESTAMP NOT NULL DEFAULT now(),
    channel TEXT NOT NULL CHECK (channel IN ('email','sms')),
    payload JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('sent','failed'))
);