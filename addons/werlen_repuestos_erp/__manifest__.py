{
    'name': 'Werlen Repuestos ERP',
    'version': '0.1.0',
    'description': 'Logistics flow for sales invoices at Werlen Repuestos.',
    'author': 'Werlen Alexander',
    'depends': ['base', 'contacts', 'mail', 'web'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'data/accounting/default_invoice_types.xml',
        'data/accounting/default_payment_methods.xml',
        'data/logistics_sales/default_points_of_sale.xml',
        'data/general/default_cities.xml',
        'data/general/default_contacts.xml',
        'data/users/default_users.xml',
        'data/parameters/param_manual_invoice_point_of_sale.xml',
        'data/parameters/param_max_hours_passed_to_allow_undo_preparation_status.xml',
        'data/parameters/param_max_hours_passed_to_allow_undo_hand_out.xml',
    ],
    'application': True
}
