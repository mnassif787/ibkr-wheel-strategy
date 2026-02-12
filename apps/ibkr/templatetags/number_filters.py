from django import template

register = template.Library()

@register.filter(name='intcomma')
def intcomma(value):
    """
    Convert an integer to a string containing commas every three digits.
    For example, 3000 becomes '3,000' and 45000 becomes '45,000'.
    """
    try:
        value = int(float(value))
        return "{:,}".format(value)
    except (ValueError, TypeError):
        return value
