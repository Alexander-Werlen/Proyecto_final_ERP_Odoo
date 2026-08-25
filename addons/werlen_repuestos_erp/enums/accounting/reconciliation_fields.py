OUTGOING_MODELS = [
    ('invoice_out', 'Factura emitida'),
    ('payment_line', 'Pago'),
    ('account_payment', 'Recibo CC'),
]

INCOMMING_MODELS = [
    ('credit_note_out', 'Nota de crédito'),
    ('payment_line', 'Pago'),
    ('check', 'Cheque'),
]

INCOMMING_FIELDS = [
    'credit_note_out_id',
    'payment_line_in_id',
    'check_id',
]

OUTGOING_FIELDS = [
    'payment_line_out_id',
    'invoice_out_id',
    'account_payment_id',
]

MODEL_IN_TO_FIELD = {
    'credit_note_out': 'credit_note_out_id',
    'payment_line': 'payment_line_in_id',
    'check': 'check_id',
}

MODEL_OUT_TO_FIELD = {
    'payment_line': 'payment_line_out_id',
    'invoice_out': 'invoice_out_id',
    'account_payment': 'account_payment_id',
}
