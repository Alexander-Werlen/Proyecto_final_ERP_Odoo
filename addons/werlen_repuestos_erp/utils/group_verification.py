from odoo.exceptions import UserError

def user_has_any_group(user, groups):
    return any(user.has_group(group) for group in groups)


def ensure_user_in_groups(user, groups, error_message=None):
    if not user_has_any_group(user, groups):
        raise UserError(
            error_message or "No tiene permisos para realizar esta acción."
        )
    
def ensure_permission_with_condition(
    user,
    groups,
    condition,
    error_message=None
):
    if user_has_any_group(user, groups) and condition():
        return

    raise UserError(
        error_message or "No tiene permisos para realizar esta acción."
    )

def ensure_write_allowed_fields(self, user, vals, EDITABLE_FIELDS_BY_GROUP, error_message=None):
        """ 
            Format example:
            EDITABLE_FIELDS_BY_GROUP = {
                'werlen_repuestos_erp.group_administration': {
                    'observations',
                },
                'werlen_repuestos_erp.group_system': {
                    '*' # all fields
                },
            } 

            vals is odoo default vals in write method (after iterating over records)
        """
        if self.env.su:
            return

        fields_to_write = set(vals.keys())

        allowed_fields = set()

        for group_xmlid, fields in EDITABLE_FIELDS_BY_GROUP.items():
            if user.has_group(group_xmlid):
                if '*' in fields:
                    return
                allowed_fields |= fields

        forbidden = fields_to_write - allowed_fields
        if forbidden:
            if error_message:
                raise UserError(error_message)
            
            raise UserError(
                "No tiene permisos suficientes para modificar estos campos."
            )
        

def display_warning_toast(title="Advertencia", message="Acción no permitida."):
    return {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'title': title,
            'message': message,
            'type': 'warning',
            'sticky': False,
        }
    }

def display_danger_toast(self, title="Error", message="Acción no permitida."):
    return {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'title': title,
            'message': message,
            'type': 'danger',
            'sticky': True,
        }
    }